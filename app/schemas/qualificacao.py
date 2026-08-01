from datetime import datetime

from pydantic import BaseModel, ConfigDict


class QualificacaoScoreSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    conta_id: int
    decisor_id: int
    conversa_id: int | None
    score_total: float
    criterios: dict
    limiar_configurado: float
    criado_em: datetime


class ConfiguracaoQualificacaoSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    limiar_padrao: float


class ConfiguracaoQualificacaoUpsertSchema(BaseModel):
    limiar_padrao: float
