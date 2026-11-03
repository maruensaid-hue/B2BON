from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConfiguracaoComunicacaoSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    tom: str
    restricoes: list
    rascunho_resposta: bool = True
    link_agendamento: str | None = None
    criado_em: datetime
    atualizado_em: datetime


class ConfiguracaoComunicacaoUpsertSchema(BaseModel):
    tom: str
    restricoes: list[str] = []
    rascunho_resposta: bool = True
    link_agendamento: str | None = None


class ValidarTextoRequestSchema(BaseModel):
    texto: str


class ValidarTextoResponseSchema(BaseModel):
    valido: bool
    violacoes: list[str]


class AmostraResponseSchema(BaseModel):
    mensagens: list[str]
