import pytest

from app.services import faq_service
from app.services.errors import RegraNegocioViolada
from tests.fakes import FakeLLMProvider


def test_responder_usa_o_llm_com_prompt_de_sistema_sobre_a_plataforma():
    llm = FakeLLMProvider(["Você vai em Cadências, cria a cadência e clica em Ativar."])

    resposta = faq_service.responder("Como eu ativo uma cadência?", llm)

    assert resposta == "Você vai em Cadências, cria a cadência e clica em Ativar."
    assert len(llm.chamadas) == 1
    assert llm.chamadas[0].prompt == "Como eu ativo uma cadência?"
    assert llm.chamadas[0].system is not None
    assert "Cadências" in llm.chamadas[0].system


def test_responder_falha_do_llm_vira_regra_negocio_violada(monkeypatch: pytest.MonkeyPatch):
    """Mesma tradução de erro já usada em cadência (`llm_helpers.gerar`) —
    falha de infraestrutura da IA nunca vira 500 cru pro usuário."""

    class LlmQuebrado(FakeLLMProvider):
        def generate(self, request):
            from app.llm.base import LLMIndisponivel

            raise LLMIndisponivel("chave da API ausente")

    with pytest.raises(RegraNegocioViolada):
        faq_service.responder("Qualquer pergunta", LlmQuebrado())
