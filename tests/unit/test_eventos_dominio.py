"""Eventos de domínio + outbox (Fase 2, Master Prompt §77)."""

import pytest

from app.contexts.shared import events
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.evento_dominio import EventoDominio
from app.services import crm_service

TENANT = "tenant-eventos"


@pytest.fixture(autouse=True)
def _registro_limpo():
    events.cancelar_inscricoes()
    yield
    events.cancelar_inscricoes()


def _conta_e_decisor(db):
    conta = Conta(tenant_id=TENANT, nome="Conta", status="prospectada")
    db.add(conta)
    db.commit()
    decisor = Decisor(tenant_id=TENANT, conta_id=conta.id, nome="D")
    db.add(decisor)
    db.commit()
    return conta, decisor


def _tipos(db):
    return [e.tipo for e in db.query(EventoDominio).order_by(EventoDominio.id).all()]


def test_evento_e_atomico_com_a_transacao_de_negocio(db_session):
    events.publicar(db_session, events.TipoEvento.OPPORTUNITY_CREATED, TENANT, "negocio", 1)
    db_session.rollback()
    assert _tipos(db_session) == []

    events.publicar(db_session, events.TipoEvento.OPPORTUNITY_CREATED, TENANT, "negocio", 1)
    db_session.commit()
    assert _tipos(db_session) == ["OpportunityCreated"]


def test_criar_e_ganhar_negocio_publica_eventos(db_session):
    conta, decisor = _conta_e_decisor(db_session)
    ganho = next(e for e in crm_service.garantir_estagios_padrao(db_session, TENANT) if e.tipo == "ganho")
    negocio = crm_service.criar_negocio(db_session, TENANT, "7", conta.id, decisor.id, "N", valor=10.0)
    crm_service.mover_estagio(db_session, TENANT, "7", negocio.id, ganho.id)

    assert _tipos(db_session) == ["OpportunityCreated", "OpportunityStageChanged", "CustomerCreated"]
    criado = db_session.query(EventoDominio).first()
    assert criado.tenant_id == TENANT and criado.agregado_id == str(negocio.id) and criado.ator_id == "7"
    assert criado.payload["conta_id"] == conta.id
    assert criado.classificacao == "INTERNAL"


def test_segundo_ganho_da_mesma_conta_nao_repete_customer_created(db_session):
    conta, decisor = _conta_e_decisor(db_session)
    ganho = next(e for e in crm_service.garantir_estagios_padrao(db_session, TENANT) if e.tipo == "ganho")
    for nome in ("N1", "N2"):
        negocio = crm_service.criar_negocio(db_session, TENANT, None, conta.id, decisor.id, nome, valor=1.0)
        crm_service.mover_estagio(db_session, TENANT, None, negocio.id, ganho.id)
    assert _tipos(db_session).count("CustomerCreated") == 1


def test_dispatcher_entrega_aos_handlers_e_marca_processado(db_session):
    recebidos = []
    events.inscrever(events.TipoEvento.OPPORTUNITY_CREATED, lambda db, evento: recebidos.append(evento))
    events.publicar(db_session, events.TipoEvento.OPPORTUNITY_CREATED, TENANT, "negocio", 42, {"k": "v"})
    db_session.commit()

    resultado = events.processar_pendentes(db_session)

    assert resultado == {"processados": 1, "falhas": 0}
    assert recebidos[0].agregado_id == "42" and recebidos[0].payload == {"k": "v"}
    assert db_session.query(EventoDominio).one().processado_em is not None
    assert events.processar_pendentes(db_session) == {"processados": 0, "falhas": 0}


def test_handler_com_erro_nao_perde_o_evento_e_desiste_apos_o_limite(db_session):
    def explode(db, evento):
        raise RuntimeError("fora do ar")

    events.inscrever(events.TipoEvento.MESSAGE_APPROVED, explode)
    events.publicar(db_session, events.TipoEvento.MESSAGE_APPROVED, TENANT, "mensagem", 1)
    db_session.commit()

    for _ in range(events.MAX_TENTATIVAS + 2):
        events.processar_pendentes(db_session)

    evento = db_session.query(EventoDominio).one()
    assert evento.processado_em is None
    assert evento.tentativas == events.MAX_TENTATIVAS
    assert "fora do ar" in evento.ultimo_erro
