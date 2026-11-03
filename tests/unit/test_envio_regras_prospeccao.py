"""Regras de envio trazidas do harvey: checagem determinística antes de sair, e-mail deduzido segurado, descadastro escrito na resposta e
pausa da empresa inteira quando alguém dela responde."""

from datetime import UTC, datetime, timedelta

import pytest

from app.contexts.predator import optout_resposta, portao_envio
from app.models.aprovacao import Aprovacao
from app.models.cadencia import Cadencia
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.mensagem import Mensagem
from app.models.regra_auto_aprovacao import RegraAutoAprovacao
from app.providers.plan_limits.stub import StubPlanLimitsProvider
from app.services import aprovacao_service, envio_service, resposta_service

TENANT = "tenant-regras-envio"


# --- Checagem determinística ----------------------------------------------------------------------------------------------

def _codigos(conteudo, assunto=None, canal="email", permitidos=("alpha.com.br",)):
    return {p.codigo for p in portao_envio.verificar(conteudo, assunto, canal, set(permitidos))}


def test_mensagem_limpa_passa():
    assert _codigos("Oi Ana, vi que a Alpha abriu vagas de dados. Faz sentido conversarmos?") == set()


def test_variaveis_que_o_envio_preenche_nao_sao_campo_vazio():
    assert _codigos("Olá {{nome}}, vi a {{ empresa }} e seu cargo de {{cargo}}.") == set()


@pytest.mark.parametrize("texto", ["Olá {{apelido}}, tudo bem?", "Olá [NOME], tudo bem?", "Oi {primeiro_nome}", "Proposta para XXX"])
def test_campo_nao_preenchido_e_grave(texto):
    problemas = portao_envio.verificar(texto, None, "email", set())
    assert any(p.codigo == "campo_nao_preenchido" and p.grave for p in problemas)


def test_frase_batida_e_comparada_sem_acento():
    assert "frase_proibida" in _codigos("Espero que você esteja bem! Gostaria de me apresentar.")


def test_link_para_dominio_estranho_inclusive_escrito_por_extenso():
    assert "dominio_externo" in _codigos("Acesse https://golpe.xyz/oferta agora")
    assert "dominio_externo" in _codigos("Veja em golpe ponto com")
    assert "dominio_externo" not in _codigos("Detalhes em https://www.alpha.com.br/precos e no blog.alpha.com.br")


def test_email_longo_e_links_demais():
    assert "longo_demais" in _codigos("palavra " * 221)
    assert "longo_demais" not in _codigos("palavra " * 221, canal="whatsapp")
    assert "links_demais" in _codigos("alpha.com.br/a alpha.com.br/b alpha.com.br/c")


# --- Descadastro escrito na resposta --------------------------------------------------------------------------------------

@pytest.mark.parametrize("texto", [
    "SAIR", "Pare.", "Por favor, me tire da lista.", "Parem de me enviar e-mails!", "Não quero mais receber essas mensagens",
    "Bom dia,\nNão tenho interesse.\nAtt", "Não, obrigado", "descadastrar",
])
def test_pedidos_de_descadastro(texto):
    assert optout_resposta.ler(texto).optout


@pytest.mark.parametrize("texto", [
    "Não tenho interesse agora, me procure em março.", "Quero saber o preço", "Podemos parar a reunião às 15h?",
    "Obrigado pelo contato!\n\nEm 3 de nov, Ana escreveu:\n> Para não receber mais e-mails: https://x/opt-out\n> responda SAIR",
])
def test_conversa_e_citacao_nao_sao_descadastro(texto):
    assert not optout_resposta.ler(texto).optout


def test_ameaca_juridica_escalada_e_descadastro_continua_valendo():
    leitura = optout_resposta.ler("Parem de me mandar e-mail ou vou ao Procon.")
    assert leitura.optout and leitura.escalar
    assert optout_resposta.ler("Vou passar para o nosso jurídico avaliar o contrato").escalar


# --- Integração com envio e resposta --------------------------------------------------------------------------------------

def _empresa(db, *nomes_emails, status_email=None):
    conta = Conta(tenant_id=TENANT, nome="Alpha", dominio="alpha.com.br", status="prospectada")
    db.add(conta)
    db.flush()
    decisores = []
    for nome, email in nomes_emails:
        decisor = Decisor(tenant_id=TENANT, conta_id=conta.id, nome=nome, cargo="Diretora", email=email, email_status=status_email)
        db.add(decisor)
        decisores.append(decisor)
    db.flush()
    return conta, decisores


def _mensagem(db, decisor, conteudo="Oi {{nome}}, vi as vagas da {{empresa}}. Faz sentido conversar?", cadencia=None, status="aprovado"):
    mensagem = Mensagem(tenant_id=TENANT, decisor_id=decisor.id, canal="email", conteudo=conteudo, status=status,
                        agendado_para=datetime.now(UTC) - timedelta(minutes=1), cadencia_id=cadencia.id if cadencia else None)
    db.add(mensagem)
    db.flush()
    db.add(Aprovacao(tenant_id=TENANT, mensagem_id=mensagem.id, status="aprovado" if status == "aprovado" else "pendente"))
    db.commit()
    return mensagem


@pytest.fixture()
def dentro_do_horario(monkeypatch):
    monkeypatch.setattr(envio_service, "_dentro_da_janela_dias_uteis_e_horario", lambda _config: True)


def test_envio_preenche_variaveis(db_session, dentro_do_horario, fake_whatsapp, fake_email, fake_email_validacao):
    _, (ana,) = _empresa(db_session, ("Ana Beatriz Ramos", "ana@alpha.com.br"))
    _mensagem(db_session, ana)

    resultado = envio_service.processar_pendentes(db_session, TENANT, fake_whatsapp, fake_email, fake_email_validacao)

    assert resultado["enviadas"] == 1
    assert fake_email.envios[0]["corpo"].startswith("Oi Ana, vi as vagas da Alpha.")


def test_campo_desconhecido_volta_para_aprovacao(db_session, dentro_do_horario, fake_whatsapp, fake_email, fake_email_validacao):
    _, (ana,) = _empresa(db_session, ("Ana Ramos", "ana@alpha.com.br"))
    mensagem = _mensagem(db_session, ana, conteudo="Oi {{apelido}}, tudo bem?")

    resultado = envio_service.processar_pendentes(db_session, TENANT, fake_whatsapp, fake_email, fake_email_validacao)

    db_session.refresh(mensagem)
    assert resultado["devolvidas_para_revisao"] == 1 and not fake_email.envios
    assert mensagem.status == "aguardando_aprovacao" and "{{apelido}}" in mensagem.motivo_falha
    assert db_session.query(Aprovacao).filter_by(mensagem_id=mensagem.id).one().status == "pendente"


def test_email_deduzido_nao_sai_ate_ser_confirmado(db_session, dentro_do_horario, fake_whatsapp, fake_email, fake_email_validacao):
    _, (ana,) = _empresa(db_session, ("Ana Ramos", "ana.ramos@alpha.com.br"), status_email="inferido")
    mensagem = _mensagem(db_session, ana)

    resultado = envio_service.processar_pendentes(db_session, TENANT, fake_whatsapp, fake_email, fake_email_validacao)
    assert resultado["aguardando_confirmacao_email"] == 1 and not fake_email.envios
    db_session.refresh(mensagem)
    assert mensagem.status == "aprovado" and "confirme o e-mail" in mensagem.motivo_falha

    ana.email_status = "confirmado"
    db_session.commit()
    assert envio_service.processar_pendentes(db_session, TENANT, fake_whatsapp, fake_email, fake_email_validacao)["enviadas"] == 1


def test_aprovacao_automatica_retem_link_estranho(db_session):
    _, (ana,) = _empresa(db_session, ("Ana Ramos", "ana@alpha.com.br"))
    db_session.add(RegraAutoAprovacao(tenant_id=TENANT, template_id="tpl", habilitada=True))
    db_session.commit()

    limpa = aprovacao_service.criar_proposta(db_session, TENANT, None, ana.id, "email", "tpl", "Oi Ana, faz sentido conversar?", StubPlanLimitsProvider())
    suspeita = aprovacao_service.criar_proposta(db_session, TENANT, None, ana.id, "email", "tpl", "Oi Ana, veja https://golpe.xyz", StubPlanLimitsProvider())

    assert limpa.status == "aprovado"
    assert suspeita.status == "aguardando_aprovacao" and "golpe.xyz" in suspeita.motivo_falha


def test_resposta_de_um_pausa_os_colegas_so_na_cadencia_que_pede(db_session):
    conta, (ana, bruno) = _empresa(db_session, ("Ana Ramos", "ana@alpha.com.br"), ("Bruno Lima", "bruno@alpha.com.br"))
    pausa = Cadencia(tenant_id=TENANT, conta_id=conta.id, nome="Com pausa", canais=["email"], status="ativa", pausar_empresa_ao_responder=True)
    sem = Cadencia(tenant_id=TENANT, conta_id=conta.id, nome="Sem pausa", canais=["email"], status="ativa")
    db_session.add_all([pausa, sem])
    db_session.flush()
    do_bruno_pausa = _mensagem(db_session, bruno, cadencia=pausa)
    do_bruno_sem = _mensagem(db_session, bruno, cadencia=sem)

    resultado = resposta_service.marcar_resposta(db_session, TENANT, ana.id)

    db_session.refresh(do_bruno_pausa)
    db_session.refresh(do_bruno_sem)
    assert resultado["mensagens_da_empresa_pausadas"] == 1
    assert do_bruno_pausa.status == "cancelado" and "Ana Ramos" in do_bruno_pausa.motivo_falha
    assert do_bruno_sem.status == "aprovado"


def test_resposta_pedindo_para_sair_vira_optout(db_session):
    _, (ana,) = _empresa(db_session, ("Ana Ramos", "ana@alpha.com.br"))
    pendente = _mensagem(db_session, ana)

    resultado = resposta_service.ler_resposta(db_session, TENANT, ana, "Por favor, me tire da lista.", "email")

    db_session.refresh(ana)
    db_session.refresh(pendente)
    assert resultado["optout_por_resposta"] and ana.suprimido_em is not None and pendente.status == "cancelado"


def test_reclamacao_sem_optout_para_os_envios_e_nao_suprime(db_session):
    _, (ana,) = _empresa(db_session, ("Ana Ramos", "ana@alpha.com.br"))
    pendente = _mensagem(db_session, ana)

    resultado = resposta_service.ler_resposta(db_session, TENANT, ana, "Isso é spam, vou denunciar.", "email")

    db_session.refresh(ana)
    db_session.refresh(pendente)
    assert resultado["escalar"] and ana.suprimido_em is None and pendente.status == "cancelado"


def test_resposta_comum_segue_o_fluxo_normal(db_session):
    _, (ana,) = _empresa(db_session, ("Ana Ramos", "ana@alpha.com.br"))
    assert resposta_service.ler_resposta(db_session, TENANT, ana, "Quanto custa?", "email") is None
