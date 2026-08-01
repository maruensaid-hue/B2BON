from pydantic import BaseModel


class LLMRequest(BaseModel):
    prompt: str
    system: str | None = None
    max_tokens: int = 1024
    temperature: float = 1.0


class LLMResponse(BaseModel):
    content: str
    model: str
    input_tokens: int
    output_tokens: int
