from pydantic import BaseModel, field_validator


class LLMRequest(BaseModel):
    prompt: str
    system: str | None = None
    max_tokens: int = 1024
    # `None` = não enviar. Modelos atuais (Sonnet 5, Opus 4.7+, Fable)
    # rejeitam parâmetros de amostragem com 400; o AI Gateway (Fase 4) só
    # preenche `temperature` para modelos que aceitam.
    temperature: float | None = None
    # `None` = modelo padrão do provider. Preenchido pelo roteador de
    # modelos do AI Gateway (classes C1–C3).
    model: str | None = None


class LLMResponse(BaseModel):
    content: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    provider: str = "anthropic"

    @field_validator("content")
    @classmethod
    def _sem_caractere_nulo(cls, valor: str) -> str:
        """O Postgres recusa texto com o caractere nulo (\\x00). Uma resposta de IA com ele (visto em produção em 09/11/2026, na
        linha "possivel_dor" da pesquisa no site) derrubava a gravação, e com ela a rodada inteira da fila de enriquecimento."""
        return valor.replace("\x00", "")
