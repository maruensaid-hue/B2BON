from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LicencaSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    plano_id: int
    status: str
    data_inicio: datetime
    data_expiracao: datetime | None


class TenantSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    razao_social: str
    cnpj: str | None
    criado_em: datetime


class TenantComLicencaSchema(BaseModel):
    tenant: TenantSchema
    licenca: LicencaSchema


class CriarTenantRequestSchema(BaseModel):
    tenant_id: str
    razao_social: str
    cnpj: str | None = None
    plano_id: int
    nome_admin: str
    email_admin: EmailStr
    senha_admin: str = Field(min_length=8, max_length=72)


class DefinirLicencaRequestSchema(BaseModel):
    plano_id: int | None = None
    status: str | None = None
    data_expiracao: datetime | None = None
