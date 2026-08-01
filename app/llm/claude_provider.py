import anthropic

from app.core.config import settings
from app.llm.base import LLMProvider
from app.llm.schemas import LLMRequest, LLMResponse


class ClaudeProvider(LLMProvider):
    """Implementação da API Claude (Anthropic) para a camada de abstração de LLM."""

    def __init__(self) -> None:
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_model

    def generate(self, request: LLMRequest) -> LLMResponse:
        message = self._client.messages.create(
            model=self._model,
            max_tokens=request.max_tokens,
            temperature=request.temperature,
            system=request.system or anthropic.NOT_GIVEN,
            messages=[{"role": "user", "content": request.prompt}],
        )
        return LLMResponse(
            content=message.content[0].text,
            model=message.model,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
        )
