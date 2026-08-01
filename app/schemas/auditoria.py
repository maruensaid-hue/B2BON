from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditLogSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    evento_tipo: str
    entidade_tipo: str
    entidade_id: int
    ator_id: str | None
    conta_id: int | None
    canal: str | None
    detalhes: dict
    criado_em: datetime
