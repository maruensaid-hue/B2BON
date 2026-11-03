"""As quatro lacunas fechadas depois da comparação com o vídeo do harvey: resposta move o funil, rascunho que conduz à reunião, ciclo
automático de geração/ativação e descoberta alimentando o enriquecimento (este último em `test_descoberta_busca`)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.contexts.predator import sinais
from app.models.aprovacao import Aprovacao
from app.models.cadencia import Cadencia
from app.models.configuracao_comunicacao import ConfiguracaoComunicacao
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.estagio_funil import EstagioFunil
from app.models.icp import ICP
from app.models.mensagem import Mensagem
from app.models.negocio import Negocio
from app.models.oferta import Oferta
from app.models.toque_cadencia import ToqueCadencia
from app.providers.plan_limits.stub import StubPlanLimitsProvider
from app.services import cadencia_service, conversa_comercial_service, prospeccao_automatica_service
from tests.fakes import FakeLLMProvider

TENANT = "tenant-ciclo-comercial"
AGORA = datetime(2026, 11, 3, 12, tzinfo=UTC)


def _base(db, *, rascunho=True, link="https://agenda.exemplo.com.br/ana"):
    db.add(ConfiguracaoComunicacao(tenant_id=TENANT, tom="consultivo", restricoes=[], rascunho_resposta=rascunho, link_agendamento=link))
    oferta = Oferta(tenant_id=TENANT, nome="Agenda Online", descricao="agendamento online para clínicas", diferenciais=[], provas_sociais=[], ativo=True)
    db.add(oferta)
    db.flush()
    return oferta


def _conta_com_decisor(db, nome="Clínica Sorriso", icp_id=None):
    conta = Conta(tenant_id=TENANT, nome=nome, dominio=f"{nome.split()[-1].lower()}.com.br", status="prospectada", icp_id=icp_id)
    db.add(conta)
    db.flush()
    decisor = Decisor(tenant_id=TENANT, conta_id=conta.id, nome="Marina Alves", cargo="Sócia", email=f"marina@{conta.dominio}")
    db.add(decisor)
    db.flush()
    return conta, decisor


def _enviada(db, decisor, assunto="Agenda da Sorriso", cadencia_id=None):
    db.add(Mensagem(tenant_id=TENANT, decisor_id=decisor.id, canal="email", conteudo="Vi que abriram a 2ª unidade. Faz sentido conversar?",
                    assunto=assunto, status="enviado", enviado_em=AGORA, agendado_para=AGORA, cadencia_id=cadencia_id))
    db.commit()


# --- Resposta move o funil e gera rascunho --------------------------------------------------------------------------------

def test_resposta_abre_negocio_no_primeiro_estagio_e_gera_rascunho_com_a_agenda(db_session):
    _base(db_session)
    conta, marina = _conta_com_decisor(db_session)
    _enviada(db_session, marina)
    llm = FakeLLMProvider(["Que bom, Marina! Uma conversa de 20 minutos ajuda: https://agenda.exemplo.com.br/ana"])

    resultado = conversa_comercial_service.apos_resposta(db_session, TENANT, marina, "Tenho interesse, como funciona?", "email", llm,
                                                         StubPlanLimitsProvider())

    negocio = db_session.query(Negocio).filter_by(id=resultado["negocio_id"]).one()
    estagio = db_session.query(EstagioFunil).filter_by(id=negocio.estagio_id).one()
    assert negocio.conta_id == conta.id and negocio.decisor_id == marina.id and negocio.origem == "predator_resposta"
    assert estagio.ordem == 1 and estagio.tipo == "aberto"
    rascunho = db_session.query(Mensagem).filter_by(id=resultado["rascunho_mensagem_id"]).one()
    assert rascunho.status == "aguardando_aprovacao" and rascunho.cadencia_id is None and rascunho.agendado_para is not None
    assert rascunho.assunto == "Re: Agenda da Sorriso"
    prompt = llm.chamadas[0].prompt
    assert "https://agenda.exemplo.com.br/ana" in prompt and "Tenho interesse" in prompt and "dados_externos" in prompt


def test_segunda_resposta_reaproveita_o_negocio_e_nao_empilha_rascunho(db_session):
    _base(db_session)
    _, marina = _conta_com_decisor(db_session)
    _enviada(db_session, marina)
    llm = FakeLLMProvider(["Claro, Marina.", "Outra versão."])
    primeiro = conversa_comercial_service.apos_resposta(db_session, TENANT, marina, "Quanto custa?", "email", llm, StubPlanLimitsProvider())
    segundo = conversa_comercial_service.apos_resposta(db_session, TENANT, marina, "E o prazo?", "email", llm, StubPlanLimitsProvider())

    assert segundo["negocio_id"] == primeiro["negocio_id"]
    assert segundo["rascunho_mensagem_id"] is None  # já há um rascunho esperando revisão
    assert db_session.query(Negocio).count() == 1


def test_sem_link_pede_dia_e_horario_e_desligado_nao_gera(db_session):
    _base(db_session, link=None)
    _, marina = _conta_com_decisor(db_session)
    _enviada(db_session, marina)
    llm = FakeLLMProvider(["Podemos falar?"])
    conversa_comercial_service.apos_resposta(db_session, TENANT, marina, "Me liga amanhã", "email", llm, StubPlanLimitsProvider())
    assert "duas opções de dia e horário" in llm.chamadas[0].prompt

    db_session.query(ConfiguracaoComunicacao).update({"rascunho_resposta": False})
    db_session.query(Mensagem).filter_by(status="aguardando_aprovacao").delete()
    db_session.commit()
    resultado = conversa_comercial_service.apos_resposta(db_session, TENANT, marina, "Oi", "email", FakeLLMProvider(), StubPlanLimitsProvider())
    assert resultado["rascunho_mensagem_id"] is None and "negocio_id" in resultado


def test_resposta_automatica_e_contato_sem_prospeccao_nao_mexem_no_funil(db_session):
    _base(db_session)
    _, marina = _conta_com_decisor(db_session)
    assert conversa_comercial_service.apos_resposta(db_session, TENANT, marina, "Oi", "email", None, None) == {"prospeccao": False}
    _enviada(db_session, marina)
    assert conversa_comercial_service.apos_resposta(db_session, TENANT, marina, "Resposta automática: estou de férias até dia 20.",
                                                    "email", None, None) == {"resposta_automatica": True}
    assert db_session.query(Negocio).count() == 0


# --- Ciclo automático -----------------------------------------------------------------------------------------------------

def _cadencia_automatica(db, oferta, criterios=()):
    icp = ICP(tenant_id=TENANT, grupo_id="g", nome="Clínicas", segmento="saúde", porte="", regiao="SP", dores=[], gatilhos=[],
              cnae_codigos=[], ufs=[], criterios_sinais=list(criterios))
    db.add(icp)
    db.flush()
    cadencia = Cadencia(tenant_id=TENANT, icp_id=icp.id, oferta_id=oferta.id, nome="Auto", canais=["email"], status="rascunho",
                        prospeccao_automatica=True)
    db.add(cadencia)
    db.flush()
    db.add(ToqueCadencia(tenant_id=TENANT, cadencia_id=cadencia.id, ordem=1, canal="email", intervalo_dias_apos_anterior=0))
    db.commit()
    return icp, cadencia


def _enriquecida(db, conta, confirmado=1, vagas=None):
    sinais._gravar(db, TENANT, conta.id, "DOMINIO_CONFIRMADO", num=confirmado, confianca=1, fonte="verificacao_dominio", agora=AGORA)
    if vagas is not None:
        sinais._gravar(db, TENANT, conta.id, "PAGINA_VAGAS", num=vagas, confianca=0.9, fonte="pesquisa_no_site", agora=AGORA)
    db.commit()


def test_ciclo_gera_so_para_contas_enriquecidas_que_atendem_aos_criterios(db_session):
    oferta = _base(db_session)
    icp, cadencia = _cadencia_automatica(db_session, oferta, [{"codigo": "PAGINA_VAGAS", "regra": "exigir"}])
    boa, _ = _conta_com_decisor(db_session, "Clínica Boa", icp.id)
    sem_vagas, _ = _conta_com_decisor(db_session, "Clínica Parada", icp.id)
    nao_lida, _ = _conta_com_decisor(db_session, "Clínica Nova", icp.id)
    _enriquecida(db_session, boa, vagas=1)
    _enriquecida(db_session, sem_vagas, vagas=0)

    resultado = prospeccao_automatica_service.executar_para_tenant(db_session, TENANT, FakeLLMProvider(), StubPlanLimitsProvider())

    assert resultado["cadencias"][cadencia.id]["geracao"] == {"contas": [boa.id], "mensagens": 1}
    # segunda rodada: a conta já está na cadência, nada novo
    de_novo = prospeccao_automatica_service.executar_para_tenant(db_session, TENANT, FakeLLMProvider(), StubPlanLimitsProvider())
    assert de_novo["cadencias"][cadencia.id]["geracao"] == "nenhuma conta nova elegível"


def test_ciclo_ativa_quando_tudo_foi_aprovado_e_nao_antes(db_session):
    oferta = _base(db_session)
    icp, cadencia = _cadencia_automatica(db_session, oferta)
    conta, _ = _conta_com_decisor(db_session, "Clínica Boa", icp.id)
    _enriquecida(db_session, conta)
    prospeccao_automatica_service.executar_para_tenant(db_session, TENANT, FakeLLMProvider(), StubPlanLimitsProvider())

    pendente = prospeccao_automatica_service.executar_para_tenant(db_session, TENANT, FakeLLMProvider(), StubPlanLimitsProvider())
    assert pendente["cadencias"][cadencia.id]["ativacao"] is None  # ainda aguardando aprovação

    for aprovacao in db_session.query(Aprovacao).filter_by(tenant_id=TENANT).all():
        aprovacao.status = "aprovado"
    db_session.query(Mensagem).filter_by(cadencia_id=cadencia.id).update({"status": "aprovado"})
    db_session.commit()

    resultado = prospeccao_automatica_service.executar_para_tenant(db_session, TENANT, FakeLLMProvider(), StubPlanLimitsProvider())
    db_session.refresh(cadencia)
    assert resultado["cadencias"][cadencia.id]["ativacao"] == "ativada" and cadencia.status == "ativa"
    assert db_session.query(Mensagem).filter_by(cadencia_id=cadencia.id).first().agendado_para is not None


def test_fila_cheia_nao_gera_mais(db_session, monkeypatch):
    oferta = _base(db_session)
    icp, cadencia = _cadencia_automatica(db_session, oferta)
    conta, decisor = _conta_com_decisor(db_session, "Clínica Boa", icp.id)
    _enriquecida(db_session, conta)
    monkeypatch.setattr(prospeccao_automatica_service, "LIMITE_PENDENTES", 1)
    db_session.add(Mensagem(tenant_id=TENANT, decisor_id=decisor.id, canal="email", conteudo="x", status="aguardando_aprovacao", cadencia_id=cadencia.id))
    db_session.commit()

    resultado = prospeccao_automatica_service.executar_para_tenant(db_session, TENANT, FakeLLMProvider(), StubPlanLimitsProvider())

    assert "fila de aprovação cheia" in resultado["cadencias"][cadencia.id]["geracao"]


def test_ligar_exige_cadencia_de_icp(db_session):
    oferta = _base(db_session)
    _, cadencia = _cadencia_automatica(db_session, oferta)
    cadencia.icp_id = None
    db_session.commit()
    from app.services.errors import RegraNegocioViolada

    with pytest.raises(RegraNegocioViolada):
        cadencia_service.definir_prospeccao_automatica(db_session, TENANT, "1", cadencia.id, True)
