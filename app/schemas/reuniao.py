from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ReuniaoSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    conta_id: int
    decisor_id: int
    vendedor_id: str
    data_hora: datetime
    status: str
    origem_crm_id: str | None
    criado_em: datetime
