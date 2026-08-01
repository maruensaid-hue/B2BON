from datetime import datetime

from pydantic import BaseModel, ConfigDict


class QualificacaoScoreSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    conta_id: int
    decisor_id: int
    score_total: float
    criterios: dict
    limiar_configurado: float
    criado_em: datetime
