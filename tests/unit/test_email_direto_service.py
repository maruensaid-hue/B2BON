from datetime import time

import pytest

from app.core.config import settings
from app.models.configuracao_envio import ConfiguracaoEnvio
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.email_direto import EmailDireto
from app.models.email_recebido import EmailRecebido
from app.models.estagio_funil import EstagioFunil
from app.models.negocio import Negocio
from app.models.usuario import Usuario
from app.services import email_direto_service, resposta_service
from app.services.errors import NaoEncontrado, RegraNegocioViolada
from tests.fakes import FakeEmailProvider

TENANT_ID = "tenant-teste"


@pytest.fixture()
def conta_e_decisor(db_session):
    conta = Conta(tenant_id=TENANT_ID, nome="Conta Teste", status="prospectada")
    db_session.add(conta)
    db_session.flush()
    decisor = Decisor(tenant_id=TENANT_ID, conta_id=conta.id, nome="Decisor Teste", email="decisor@teste.com")
    db_session.add(decisor)
    db_session.commit()
    return conta, decisor


@pytest.fixture()
def vendedor(db_session):
    usuario = Usuario(tenant_id=TENANT_ID, nome="Vendedor Teste", email="vendedor@teste.com", papel="user")
    db_session.add(usuario)
    db_session.commit()
    return usuario


def test_enviar_com_sucesso_persiste_email_e_atividade(db_session, conta_e_decisor, vendedor):
    conta, decisor = conta_e_decisor
    provider = FakeEmailProvider()

    resultado = email_direto_service.enviar(
        db_session, TENANT_ID, vendedor, decisor.id, "Assunto de teste", "Corpo da mensagem", provider
    )

    assert resultado["status"] == "enviado"
    assert resultado["conta_nome"] == conta.nome
    assert resultado["decisor_nome"] == decisor.nome
    assert len(provider.envios) == 1
    assert provider.envios[0]["destinatario"] == decisor.email
    assert "Corpo da mensagem" in provider.envios[0]["corpo"]
    assert "Para não receber mais e-mails" in provider.envios[0]["corpo"]

    email = db_session.query(EmailDireto).one()
    assert email.status == "enviado"
    assert email.conta_id == conta.id
    # Histórico guarda o texto EXATO que saiu (com o rodapé), não uma
    # reconstrução parcial do que o vendedor digitou.
    assert "Corpo da mensagem" in email.corpo
    assert "Para não receber mais e-mails" in email.corpo
    assert resultado["corpo"] == email.corpo


def test_enviar_decisor_sem_email_levanta_regra_negocio_violada(db_session, vendedor):
    conta = Conta(tenant_id=TENANT_ID, nome="Conta Sem Email", status="prospectada")
    db_session.add(conta)
    db_session.flush()
    decisor = Decisor(tenant_id=TENANT_ID, conta_id=conta.id, nome="Sem Email")
    db_session.add(decisor)
    db_session.commit()

    with pytest.raises(RegraNegocioViolada):
        email_direto_service.enviar(db_session, TENANT_ID, vendedor, decisor.id, "Assunto", "Corpo", FakeEmailProvider())


def test_enviar_decisor_de_outro_tenant_levanta_nao_encontrado(db_session, conta_e_decisor, vendedor):
    _, decisor = conta_e_decisor

    with pytest.raises(NaoEncontrado):
        email_direto_service.enviar(db_session, "outro-tenant", vendedor, decisor.id, "Assunto", "Corpo", FakeEmailProvider())


def test_enviar_falha_do_provider_persiste_status_falhou_sem_levantar_excecao(db_session, conta_e_decisor, vendedor):
    _, decisor = conta_e_decisor
    provider = FakeEmailProvider()
    provider.falhar_proximos = 1

    resultado = email_direto_service.enviar(db_session, TENANT_ID, vendedor, decisor.id, "Assunto", "Corpo", provider)

    assert resultado["status"] == "falhou"
    assert resultado["motivo_falha"] == "falha simulada"
    email = db_session.query(EmailDireto).one()
    assert email.status == "falhou"
    assert email.enviado_em is None


def test_enviar_usa_assinatura_pessoal_quando_configurada(db_session, conta_e_decisor, vendedor):
    _, decisor = conta_e_decisor
    vendedor.email_assinatura = "Atenciosamente,\nVendedor Teste"
    db_session.commit()
    provider = FakeEmailProvider()

    email_direto_service.enviar(db_session, TENANT_ID, vendedor, decisor.id, "Assunto", "Corpo", provider)

    assert "Atenciosamente" in provider.envios[0]["corpo"]


def test_enviar_cai_na_assinatura_do_tenant_quando_pessoal_nao_configurada(db_session, conta_e_decisor, vendedor):
    _, decisor = conta_e_decisor
    db_session.add(
        ConfiguracaoEnvio(
            tenant_id=TENANT_ID,
            remetente_nome="Empresa Teste",
            remetente_email="contato@empresateste.com",
            assinatura="Equipe Empresa Teste",
            horario_inicio=time(8, 0),
            horario_fim=time(18, 0),
        )
    )
    db_session.commit()
    provider = FakeEmailProvider()

    email_direto_service.enviar(db_session, TENANT_ID, vendedor, decisor.id, "Assunto", "Corpo", provider)

    assert "Equipe Empresa Teste" in provider.envios[0]["corpo"]
    assert provider.envios[0]["remetente_email"] == "contato@empresateste.com"


def test_listar_enviados_usuario_comum_ve_so_os_proprios(db_session, conta_e_decisor, vendedor):
    _, decisor = conta_e_decisor
    outro_vendedor = Usuario(tenant_id=TENANT_ID, nome="Outro Vendedor", email="outro@teste.com", papel="user")
    db_session.add(outro_vendedor)
    db_session.commit()
    email_direto_service.enviar(db_session, TENANT_ID, vendedor, decisor.id, "Meu e-mail", "Corpo", FakeEmailProvider())
    email_direto_service.enviar(db_session, TENANT_ID, outro_vendedor, decisor.id, "E-mail do outro", "Corpo", FakeEmailProvider())

    resultado = email_direto_service.listar_enviados(db_session, TENANT_ID, vendedor)

    assert len(resultado) == 1
    assert resultado[0]["assunto"] == "Meu e-mail"


def test_listar_enviados_admin_ve_todos(db_session, conta_e_decisor, vendedor):
    _, decisor = conta_e_decisor
    admin = Usuario(tenant_id=TENANT_ID, nome="Admin Teste", email="admin@teste.com", papel="admin")
    db_session.add(admin)
    db_session.commit()
    email_direto_service.enviar(db_session, TENANT_ID, vendedor, decisor.id, "Meu e-mail", "Corpo", FakeEmailProvider())
    email_direto_service.enviar(db_session, TENANT_ID, admin, decisor.id, "E-mail do admin", "Corpo", FakeEmailProvider())

    resultado = email_direto_service.listar_enviados(db_session, TENANT_ID, admin)

    assert len(resultado) == 2


def test_configuracao_pessoal_get_e_set(db_session, vendedor):
    assert email_direto_service.obter_configuracao(vendedor) == {"email_nome_exibicao": None, "email_assinatura": None}

    resultado = email_direto_service.atualizar_configuracao(db_session, vendedor, "Vendedor Exibido", "Att, Vendedor")

    assert resultado == {"email_nome_exibicao": "Vendedor Exibido", "email_assinatura": "Att, Vendedor"}


def test_enviar_sem_dominio_respostas_nao_troca_reply_to(db_session, conta_e_decisor, vendedor, monkeypatch):
    """Comportamento de sempre — sem `dominio_respostas` configurado, a
    resposta continua caindo direto na caixa real do tenant."""
    monkeypatch.setattr(settings, "dominio_respostas", "")
    _, decisor = conta_e_decisor
    provider = FakeEmailProvider()

    email_direto_service.enviar(db_session, TENANT_ID, vendedor, decisor.id, "Assunto", "Corpo", provider)

    assert provider.envios[0]["reply_to"] is None


def test_enviar_com_dominio_respostas_troca_reply_to(db_session, conta_e_decisor, vendedor, monkeypatch):
    monkeypatch.setattr(settings, "dominio_respostas", "respostas.teste.com.br")
    _, decisor = conta_e_decisor
    provider = FakeEmailProvider()

    email_direto_service.enviar(db_session, TENANT_ID, vendedor, decisor.id, "Assunto", "Corpo", provider)

    reply_to = provider.envios[0]["reply_to"]
    assert reply_to is not None
    assert reply_to.startswith("resp+")
    assert reply_to.endswith("@respostas.teste.com.br")
    token = reply_to.removeprefix("resp+").removesuffix("@respostas.teste.com.br")
    tenant_id, decisor_id = resposta_service.validar_token_resposta(token)
    assert tenant_id == TENANT_ID
    assert decisor_id == decisor.id


def test_processar_recebido_persiste_registra_atividade_e_retransmite(db_session, conta_e_decisor):
    conta, decisor = conta_e_decisor
    db_session.add(
        ConfiguracaoEnvio(
            tenant_id=TENANT_ID,
            remetente_nome="Empresa Teste",
            remetente_email="contato@empresateste.com",
            assinatura="",
            horario_inicio=time(8, 0),
            horario_fim=time(18, 0),
        )
    )
    db_session.commit()
    provider = FakeEmailProvider()

    email = email_direto_service.processar_recebido(
        db_session, TENANT_ID, decisor.id, "cliente@empresa.com", "Re: Proposta", "Aceito!", provider
    )

    assert email.decisor_id == decisor.id
    assert email.conta_id == conta.id
    assert db_session.query(EmailRecebido).count() == 1
    # Retransmissão pro e-mail real do tenant — nunca perde a resposta.
    assert len(provider.envios) == 1
    assert provider.envios[0]["destinatario"] == "contato@empresateste.com"
    assert "Aceito!" in provider.envios[0]["corpo"]


def test_processar_recebido_sem_decisor_ainda_retransmite(db_session):
    """Token válido (assinatura confere) mas decisor foi excluído depois
    — ainda sabemos o tenant, então ainda retransmitimos; só não tem
    vínculo de conta/decisor no registro."""
    provider = FakeEmailProvider()

    email = email_direto_service.processar_recebido(
        db_session, TENANT_ID, 999999, "cliente@empresa.com", "Assunto", "Corpo", provider
    )

    assert email.decisor_id is None
    assert email.conta_id is None
    # Sem ConfiguracaoEnvio nem SENDGRID_REMETENTE_EMAIL configurado em
    # teste, a retransmissão é pulada (destinatário vazio) — sem erro.
    assert db_session.query(EmailRecebido).count() == 1


def test_listar_recebidos_usuario_comum_ve_so_contas_proprias(db_session, conta_e_decisor, vendedor):
    conta, decisor = conta_e_decisor
    conta.vendedor_usuario_id = vendedor.id
    db_session.commit()
    email_direto_service.processar_recebido(
        db_session, TENANT_ID, decisor.id, "cliente@empresa.com", "Assunto", "Corpo", FakeEmailProvider()
    )
    outro_vendedor = Usuario(tenant_id=TENANT_ID, nome="Outro", email="outro@teste.com", papel="user")
    db_session.add(outro_vendedor)
    db_session.commit()

    assert len(email_direto_service.listar_recebidos(db_session, TENANT_ID, vendedor)) == 1
    assert len(email_direto_service.listar_recebidos(db_session, TENANT_ID, outro_vendedor)) == 0


def test_arquivar_conversa_marca_pendentes_e_registra_atividade_consolidada(db_session, conta_e_decisor, vendedor):
    conta, decisor = conta_e_decisor
    email_direto_service.enviar(db_session, TENANT_ID, vendedor, decisor.id, "Assunto 1", "Corpo 1", FakeEmailProvider())
    email_direto_service.processar_recebido(
        db_session, TENANT_ID, decisor.id, "cliente@empresa.com", "Assunto 2", "Corpo 2", FakeEmailProvider()
    )

    resultado = email_direto_service.arquivar_conversa(db_session, TENANT_ID, vendedor, decisor.id)

    assert resultado == {"enviados_arquivados": 1, "recebidos_arquivados": 1}
    assert db_session.query(EmailDireto).filter_by(decisor_id=decisor.id).one().arquivado_em is not None
    assert db_session.query(EmailRecebido).filter_by(decisor_id=decisor.id).one().arquivado_em is not None
    assert email_direto_service.listar_enviados(db_session, TENANT_ID, vendedor) == []
    assert email_direto_service.listar_recebidos(db_session, TENANT_ID, vendedor) == []


def test_arquivar_conversa_idempotente_sem_pendencias(db_session, conta_e_decisor, vendedor):
    _, decisor = conta_e_decisor
    email_direto_service.enviar(db_session, TENANT_ID, vendedor, decisor.id, "Assunto", "Corpo", FakeEmailProvider())
    email_direto_service.arquivar_conversa(db_session, TENANT_ID, vendedor, decisor.id)

    resultado = email_direto_service.arquivar_conversa(db_session, TENANT_ID, vendedor, decisor.id)

    assert resultado == {"enviados_arquivados": 0, "recebidos_arquivados": 0}


def test_arquivar_conversa_registra_atividade_so_em_negocios_abertos(db_session, conta_e_decisor, vendedor):
    from app.models.atividade import Atividade

    conta, decisor = conta_e_decisor
    estagio_aberto = EstagioFunil(tenant_id=TENANT_ID, nome="Descoberta", ordem=1, tipo="aberto")
    estagio_ganho = EstagioFunil(tenant_id=TENANT_ID, nome="Ganho", ordem=2, tipo="ganho")
    db_session.add_all([estagio_aberto, estagio_ganho])
    db_session.flush()
    negocio_aberto = Negocio(
        tenant_id=TENANT_ID, conta_id=conta.id, decisor_id=decisor.id, estagio_id=estagio_aberto.id,
        nome="Negócio Aberto", valor=100.0, probabilidade=50, origem="manual",
    )
    negocio_ganho = Negocio(
        tenant_id=TENANT_ID, conta_id=conta.id, decisor_id=decisor.id, estagio_id=estagio_ganho.id,
        nome="Negócio Ganho", valor=200.0, probabilidade=100, origem="manual",
    )
    db_session.add_all([negocio_aberto, negocio_ganho])
    db_session.commit()
    email_direto_service.enviar(db_session, TENANT_ID, vendedor, decisor.id, "Assunto", "Corpo", FakeEmailProvider())

    email_direto_service.arquivar_conversa(db_session, TENANT_ID, vendedor, decisor.id)

    atividades_negocio_aberto = db_session.query(Atividade).filter_by(negocio_id=negocio_aberto.id).all()
    atividades_negocio_ganho = db_session.query(Atividade).filter_by(negocio_id=negocio_ganho.id).all()
    assert any("arquivada" in a.descricao for a in atividades_negocio_aberto)
    assert not any("arquivada" in a.descricao for a in atividades_negocio_ganho)


def test_listar_pendentes_arquivamento_agrupa_por_decisor(db_session, conta_e_decisor, vendedor):
    conta, decisor = conta_e_decisor
    conta.vendedor_usuario_id = vendedor.id
    db_session.commit()
    email_direto_service.enviar(db_session, TENANT_ID, vendedor, decisor.id, "Assunto 1", "Corpo 1", FakeEmailProvider())
    email_direto_service.enviar(db_session, TENANT_ID, vendedor, decisor.id, "Assunto 2", "Corpo 2", FakeEmailProvider())
    email_direto_service.processar_recebido(
        db_session, TENANT_ID, decisor.id, "cliente@empresa.com", "Assunto 3", "Corpo 3", FakeEmailProvider()
    )

    resultado = email_direto_service.listar_pendentes_arquivamento(db_session, TENANT_ID, vendedor)

    assert len(resultado) == 1
    assert resultado[0]["decisor_id"] == decisor.id
    assert resultado[0]["total_enviados"] == 2
    assert resultado[0]["total_recebidos"] == 1
