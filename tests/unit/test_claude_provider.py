from unittest.mock import MagicMock, patch

import pytest

from app.core.config import settings
from app.llm.base import LLMIndisponivel
from app.llm.claude_provider import ClaudeProvider
from app.llm.schemas import LLMRequest


def _bloco(tipo: str, texto: str = "") -> MagicMock:
    bloco = MagicMock()
    bloco.type = tipo
    bloco.text = texto
    return bloco


def _provider_com_resposta(mensagem_falsa: MagicMock) -> ClaudeProvider:
    with patch("app.llm.claude_provider.anthropic.Anthropic", MagicMock()) as anthropic_mock:
        anthropic_mock.return_value.messages.create.return_value = mensagem_falsa
        provider = ClaudeProvider()
    provider._client.messages.create.return_value = mensagem_falsa
    return provider


def test_generate_pula_bloco_de_pensamento_e_usa_o_bloco_de_texto(monkeypatch: pytest.MonkeyPatch):
    """Raio-X de produção real: quando o modelo "pensa" antes de responder
    (prompt complexo, ex.: enriquecimento de site institucional denso), o
    primeiro bloco da resposta é um ThinkingBlock sem atributo `.text` —
    pegar sempre `content[0].text` estourava `AttributeError`, virando um
    500 cru em vez do resumo esperado."""
    monkeypatch.setattr(settings, "anthropic_api_key", "chave-teste")
    mensagem_falsa = MagicMock()
    mensagem_falsa.content = [_bloco("thinking"), _bloco("text", "Resumo gerado.")]
    mensagem_falsa.model = "claude-sonnet-5"
    mensagem_falsa.usage.input_tokens = 100
    mensagem_falsa.usage.output_tokens = 20
    provider = _provider_com_resposta(mensagem_falsa)

    resposta = provider.generate(LLMRequest(prompt="qualquer coisa"))

    assert resposta.content == "Resumo gerado."


def test_generate_sem_nenhum_bloco_de_texto_levanta_llm_indisponivel(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "anthropic_api_key", "chave-teste")
    mensagem_falsa = MagicMock()
    mensagem_falsa.content = [_bloco("thinking")]
    provider = _provider_com_resposta(mensagem_falsa)

    with pytest.raises(LLMIndisponivel):
        provider.generate(LLMRequest(prompt="qualquer coisa"))


def test_generate_com_typeerror_da_sdk_levanta_llm_indisponivel(monkeypatch: pytest.MonkeyPatch):
    """Raio-X de produção real (2026-08-27): sem lock file, a versão da SDK
    da Anthropic instalada em produção pode divergir da testada localmente
    (camada Docker de `pip install` fica cacheada enquanto pyproject.toml
    não muda) — uma mudança de assinatura do `messages.create` estourava
    `TypeError` cru até o handler genérico de 500, em vez do erro de
    negócio claro que já existe pra falha da IA."""
    monkeypatch.setattr(settings, "anthropic_api_key", "chave-teste")
    with patch("app.llm.claude_provider.anthropic.Anthropic", MagicMock()) as anthropic_mock:
        anthropic_mock.return_value.messages.create.side_effect = TypeError(
            "Messages.create() got an unexpected keyword argument 'temperature'"
        )
        provider = ClaudeProvider()
    provider._client.messages.create.side_effect = TypeError(
        "Messages.create() got an unexpected keyword argument 'temperature'"
    )

    with pytest.raises(LLMIndisponivel):
        provider.generate(LLMRequest(prompt="qualquer coisa"))


def test_cliente_e_criado_com_timeout_explicito():
    """Raio-X de produção real: sem timeout explícito, um prompt grande
    (ex.: enriquecimento de site) podia ficar pendurado além do timeout
    do proxy do Render, que devolve resposta sem os cabeçalhos de CORS —
    aparecia pro usuário como erro de CORS em vez do erro de negócio
    claro que a camada de LLMIndisponivel já trata."""
    with patch("app.llm.claude_provider.anthropic.Anthropic", MagicMock()) as anthropic_mock:
        ClaudeProvider()

    _, kwargs = anthropic_mock.call_args
    assert kwargs["timeout"] == 25.0
