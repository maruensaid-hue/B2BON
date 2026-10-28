from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BloqueioContatoSchema(BaseModel):
    """Entrada da lista de bloqueio da empresa: e-mail e/ou telefone de quem pediu para não receber."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str | None
    telefone: str | None
    motivo: str
    origem: str
    criado_em: datetime
