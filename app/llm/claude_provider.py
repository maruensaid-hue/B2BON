import anthropic

from app.core.config import settings
from app.llm.base import LLMIndisponivel, LLMProvider
from app.llm.schemas import LLMRequest, LLMResponse


class ClaudeProvider(LLMProvider):
    """Implementação da API Claude (Anthropic) para a camada de abstração de LLM."""

    def __init__(self) -> None:
        # Timeout explícito — sem isto, uma chamada lenta (prompt grande,
        # ex.: enriquecimento de site com várias páginas) podia ficar
        # pendurada além do timeout do proxy do Render, que devolve uma
        # resposta sem os cabeçalhos de CORS da nossa API e aparece pro
        # usuário como erro de CORS (raio-X de produção real) em vez do
        # erro de negócio claro que `LLMIndisponivel`/`RegraNegocioViolada`
        # já produzem.
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=25.0)
        self._model = settings.anthropic_model

    def generate(self, request: LLMRequest) -> LLMResponse:
        if not settings.anthropic_api_key:
            raise LLMIndisponivel("ANTHROPIC_API_KEY não configurada no servidor.")
        try:
            message = self._client.messages.create(
                model=self._model,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                system=request.system or anthropic.NOT_GIVEN,
                messages=[{"role": "user", "content": request.prompt}],
            )
        except anthropic.AnthropicError as erro:
            raise LLMIndisponivel(f"Falha ao chamar a IA: {erro}") from erro

        # `message.content[0]` nem sempre é o texto final — em prompts mais
        # complexos (ex.: site institucional denso) o modelo pode pensar
        # antes de responder, e o primeiro bloco vira um `ThinkingBlock`
        # (sem atributo `.text`), com a resposta de verdade só num bloco
        # seguinte. Raio-X de produção real: `content[0].text` estourava
        # `AttributeError` sempre que isso acontecia, virando um 500 cru
        # em vez do resumo esperado.
        texto = next((bloco.text for bloco in message.content if bloco.type == "text"), None)
        if texto is None:
            raise LLMIndisponivel("A IA não retornou texto na resposta.")

        return LLMResponse(
            content=texto,
            model=message.model,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
        )
