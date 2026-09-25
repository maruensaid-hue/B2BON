import pytest

from app.services import faq_service
from app.services.errors import RegraNegocioViolada
from tests.fakes import FakeLLMProvider

TENANT_FAQ = "tenant-faq"


def test_responder_usa_o_llm_com_prompt_de_sistema_sobre_a_plataforma(db_session):
    llm = FakeLLMProvider(["Você vai em Cadências, cria a cadência e clica em Ativar."])

    resposta = faq_service.responder(db_session, TENANT_FAQ, None, "Como eu ativo uma cadência?", llm)

    assert resposta == "Você vai em Cadências, cria a cadência e clica em Ativar."
    assert len(llm.chamadas) == 1
    assert llm.chamadas[0].prompt == "Como eu ativo uma cadência?"
    assert llm.chamadas[0].system is not None
    assert "Cadências" in llm.chamadas[0].system


def test_responder_com_historico_inclui_turnos_anteriores_no_prompt(db_session):
    llm = FakeLLMProvider(["Sim, o CRM já mostra isso no funil."])

    resposta = faq_service.responder(
        db_session, TENANT_FAQ, None,
        "E isso aparece no Dashboard?",
        llm,
        historico=[("usuario", "Como funciona o funil do CRM?"), ("ia", "Cada estágio vira uma coluna do Kanban.")],
    )

    assert resposta == "Sim, o CRM já mostra isso no funil."
    prompt = llm.chamadas[0].prompt
    assert "Como funciona o funil do CRM?" in prompt
    assert "Cada estágio vira uma coluna do Kanban." in prompt
    assert "E isso aparece no Dashboard?" in prompt


def test_responder_trunca_historico_nos_ultimos_seis_turnos(db_session):
    llm = FakeLLMProvider(["resposta"])
    historico = [("usuario" if i % 2 == 0 else "ia", f"turno {i}") for i in range(10)]

    faq_service.responder(db_session, TENANT_FAQ, None, "pergunta nova", llm, historico=historico)

    prompt = llm.chamadas[0].prompt
    assert "turno 0" not in prompt
    assert "turno 3" not in prompt
    assert "turno 4" in prompt
    assert "turno 9" in prompt


def test_responder_sem_historico_mantem_prompt_igual_a_pergunta(db_session):
    llm = FakeLLMProvider(["resposta"])

    faq_service.responder(db_session, TENANT_FAQ, None, "pergunta isolada", llm, historico=None)

    assert llm.chamadas[0].prompt == "pergunta isolada"


def test_responder_falha_do_llm_vira_regra_negocio_violada(db_session, monkeypatch: pytest.MonkeyPatch):
    """Mesma tradução de erro já usada em cadência (`llm_helpers.gerar`) —
    falha de infraestrutura da IA nunca vira 500 cru pro usuário."""

    class LlmQuebrado(FakeLLMProvider):
        def generate(self, request):
            from app.llm.base import LLMIndisponivel

            raise LLMIndisponivel("chave da API ausente")

    with pytest.raises(RegraNegocioViolada):
        faq_service.responder(db_session, TENANT_FAQ, None, "Qualquer pergunta", LlmQuebrado())
