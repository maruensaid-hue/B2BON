from unittest.mock import MagicMock, patch

from app.llm.claude_provider import ClaudeProvider


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
