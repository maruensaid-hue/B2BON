from datetime import date

from pydantic import BaseModel, Field


class CriarParcelaRequestSchema(BaseModel):
    valor: float = Field(gt=0)
    vencimento: date
    observacao: str | None = Field(default=None, max_length=300)


class AtualizarParcelaRequestSchema(CriarParcelaRequestSchema):
    pago_em: date | None = None


class CriarNotaDailyRequestSchema(BaseModel):
    texto: str = Field(min_length=1, max_length=4000)
    exibir_em: date | None = None  # vazio = dia seguinte (Brasília)


class ConcluirNotaDailyRequestSchema(BaseModel):
    concluida: bool = True
