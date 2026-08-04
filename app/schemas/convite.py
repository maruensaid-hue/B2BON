from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ConviteCadastroSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    codigo: str
    papel_concedido: str
    status: str
    validade_em: datetime | None
    usado_por_usuario_id: int | None
    criado_em: datetime


class GerarConviteRequestSchema(BaseModel):
    papel_concedido: str = "user"
    validade_horas: int | None = 168


class ConviteVitrineSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id_origem: str
    codigo: str
    status: str
    validade_em: datetime | None
    tenant_id_gerado: str | None
    criado_em: datetime


class GerarConviteVitrineRequestSchema(BaseModel):
    validade_horas: int | None = 168
