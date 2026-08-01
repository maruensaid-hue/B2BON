from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConfiguracaoNotificacaoSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    vendedor_id: str
    vendedor_telefone: str


class ConfiguracaoNotificacaoUpsertSchema(BaseModel):
    vendedor_id: str
    vendedor_telefone: str


class NotificacaoVendedorSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    conversa_id: int
    vendedor_id: str
    resumo: str
    criado_em: datetime
    primeiro_contato_em: datetime | None
    sla_segundos: float | None = None
