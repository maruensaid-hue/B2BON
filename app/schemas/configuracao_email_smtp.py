from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConfiguracaoEmailSmtpSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    host: str
    porta: int
    usuario: str
    usar_tls: bool
    senha_mascarada: str
    criado_em: datetime
    atualizado_em: datetime


class ConfiguracaoEmailSmtpUpsertSchema(BaseModel):
    host: str
    porta: int
    usuario: str
    usar_tls: bool = True
    senha: str | None = None
