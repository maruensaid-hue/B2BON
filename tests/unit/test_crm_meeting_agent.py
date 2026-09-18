from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.oferta import Oferta
from app.services import atividade_service, crm_service
from app.services.errors import NaoEncontrado
from tests.fakes import FakeLLMProvider

TENANT_ID = "tenant-teste"


def _criar_negocio(db_session, cargo_decisor: str | None = "Diretor Financeiro", oferta: Oferta | None = None):
    conta = Conta(tenant_id=TENANT_ID, nome="Conta Teste", status="priorizada", segmento="saude", porte="grande")
    db_session.add(conta)
    db_session.flush()
    decisor = Decisor(tenant_id=TENANT_ID, conta_id=conta.id, nome="Decisor Teste", cargo=cargo_decisor)
    db_session.add(decisor)
    db_session.commit()

    negocio = crm_service.criar_negocio(
        db_session, TENANT_ID, None, conta.id, decisor.id, "Negócio Teste", valor=10000,
        oferta_id=oferta.id if oferta else None,
    )
    return conta, decisor, negocio


def test_gerar_meeting_brief_chama_llm_com_dados_do_negocio(db_session):
    conta, decisor, negocio = _criar_negocio(db_session)
    llm = FakeLLMProvider()

    resultado = crm_service.gerar_meeting_brief(db_session, TENANT_ID, None, negocio.id, llm)

    assert "brief" in resultado
    assert len(llm.chamadas) == 1
    prompt = llm.chamadas[0].prompt
    assert "Negócio Teste" in prompt
    assert "Decisor Teste" in prompt
    assert "Diretor Financeiro" in prompt


def test_gerar_meeting_brief_cita_papel_sugerido_quando_nao_confirmado(db_session):
    conta, decisor, negocio = _criar_negocio(db_session, cargo_decisor="Diretor Financeiro")
    llm = FakeLLMProvider()

    crm_service.gerar_meeting_brief(db_session, TENANT_ID, None, negocio.id, llm)

    assert "ECONOMIC_BUYER" in llm.chamadas[0].prompt
    assert "não confirmado" in llm.chamadas[0].prompt


def test_gerar_meeting_brief_cita_papel_confirmado(db_session):
    from app.services import conta_service

    conta, decisor, negocio = _criar_negocio(db_session)
    conta_service.confirmar_papel_decisor(db_session, TENANT_ID, None, conta.id, decisor.id, "DECISION_MAKER")
    llm = FakeLLMProvider()

    crm_service.gerar_meeting_brief(db_session, TENANT_ID, None, negocio.id, llm)

    assert "DECISION_MAKER" in llm.chamadas[0].prompt
    assert "não confirmado" not in llm.chamadas[0].prompt


def test_gerar_meeting_brief_cita_atividades_recentes(db_session):
    conta, decisor, negocio = _criar_negocio(db_session)
    atividade_service.registrar(
        db_session, TENANT_ID, conta_id=conta.id, negocio_id=negocio.id, tipo="ligacao", descricao="Ligação de descoberta"
    )
    llm = FakeLLMProvider()

    crm_service.gerar_meeting_brief(db_session, TENANT_ID, None, negocio.id, llm)

    assert "Ligação de descoberta" in llm.chamadas[0].prompt


def test_gerar_meeting_brief_cita_oferta_vinculada(db_session):
    oferta = Oferta(tenant_id=TENANT_ID, nome="Backup Imutável", descricao="Solução de backup em nuvem", ativo=True)
    db_session.add(oferta)
    db_session.commit()
    conta, decisor, negocio = _criar_negocio(db_session, oferta=oferta)
    llm = FakeLLMProvider()

    crm_service.gerar_meeting_brief(db_session, TENANT_ID, None, negocio.id, llm)

    assert "Backup Imutável" in llm.chamadas[0].prompt


def test_gerar_meeting_brief_negocio_inexistente_levanta_erro(db_session):
    llm = FakeLLMProvider()
    try:
        crm_service.gerar_meeting_brief(db_session, TENANT_ID, None, 9999, llm)
        assert False, "deveria ter levantado NaoEncontrado"
    except NaoEncontrado:
        pass


def test_gerar_meeting_brief_isolamento_tenant(db_session):
    conta, decisor, negocio = _criar_negocio(db_session)
    llm = FakeLLMProvider()

    try:
        crm_service.gerar_meeting_brief(db_session, "tenant-outro", None, negocio.id, llm)
        assert False, "deveria ter levantado NaoEncontrado"
    except NaoEncontrado:
        pass
