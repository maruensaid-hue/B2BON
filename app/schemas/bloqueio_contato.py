from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BloqueioContatoSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str | None
    telefone: str | None
    motivo: str
    origem: str
    criado_em: datetime
