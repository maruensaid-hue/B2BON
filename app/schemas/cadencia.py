from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CadenciaSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    conta_id: int
    nome: str
    canais: list
    status: str
    data_inicio: datetime | None
    criado_em: datetime
