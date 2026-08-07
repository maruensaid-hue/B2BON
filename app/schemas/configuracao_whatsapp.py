from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConfiguracaoWhatsAppSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    phone_number_id: str
    business_account_id: str
    access_token_mascarado: str
    criado_em: datetime
    atualizado_em: datetime


class ConfiguracaoWhatsAppUpsertSchema(BaseModel):
    phone_number_id: str
    business_account_id: str
    access_token: str | None = None
