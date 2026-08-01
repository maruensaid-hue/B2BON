from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TurnoConversaSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conversa_id: int
    direcao: str
    conteudo: str
    criado_em: datetime


class ConversaQualificacaoSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    conta_id: int
    decisor_id: int
    canal: str
    etapa_atual: str
    status: str
    motivo_devolucao: str | None
    transferido_em: datetime | None
    criado_em: datetime
    atualizado_em: datetime


class ConversaComTurnosSchema(BaseModel):
    conversa: ConversaQualificacaoSchema
    turnos: list[TurnoConversaSchema]


class DevolverLeadRequestSchema(BaseModel):
    motivo: str
    cadencia_nutricao_id: int
