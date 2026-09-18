from app.llm.schemas import LLMRequest
from app.models.registro_uso_ia import RegistroUsoIa
from app.services import llm_helpers
from app.services.errors import RegraNegocioViolada
from tests.fakes import FakeLLMProvider

TENANT_ID = "tenant-teste"


def test_gerar_e_registrar_persiste_tokens_e_latencia(db_session):
    llm = FakeLLMProvider(["resposta qualquer"])

    resultado = llm_helpers.gerar_e_registrar(
        db_session, TENANT_ID, "corporate_ai_agent", llm, LLMRequest(prompt="pergunta")
    )

    assert resultado.content == "resposta qualquer"
    registros = db_session.query(RegistroUsoIa).filter_by(tenant_id=TENANT_ID).all()
    assert len(registros) == 1
    assert registros[0].agente == "corporate_ai_agent"
    assert registros[0].tokens_entrada == 0
    assert registros[0].tokens_saida == 0
    assert registros[0].latencia_ms >= 0


def test_gerar_e_registrar_isolamento_tenant(db_session):
    llm = FakeLLMProvider(["resposta"])

    llm_helpers.gerar_e_registrar(db_session, TENANT_ID, "meeting_agent", llm, LLMRequest(prompt="pergunta"))

    registros_outro_tenant = db_session.query(RegistroUsoIa).filter_by(tenant_id="tenant-outro").all()
    assert registros_outro_tenant == []


def test_gerar_e_registrar_com_llm_indisponivel_nao_persiste_nada(db_session, monkeypatch):
    llm = FakeLLMProvider(["resposta"])

    def _generate_falha(request):
        from app.llm.base import LLMIndisponivel

        raise LLMIndisponivel("sem chave configurada")

    monkeypatch.setattr(llm, "generate", _generate_falha)

    try:
        llm_helpers.gerar_e_registrar(db_session, TENANT_ID, "sales_strategy_agent", llm, LLMRequest(prompt="x"))
        assert False, "deveria ter levantado RegraNegocioViolada"
    except RegraNegocioViolada:
        pass

    assert db_session.query(RegistroUsoIa).filter_by(tenant_id=TENANT_ID).all() == []
