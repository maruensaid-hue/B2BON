from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UsuarioSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    nome: str
    email: str
    papel: str
    ativo: bool
    criado_em: datetime
    ultimo_login_em: datetime | None
    termos_aceitos_em: datetime | None


class LoginRequestSchema(BaseModel):
    email: EmailStr
    senha: str = Field(min_length=1, max_length=72)


class LoginGoogleRequestSchema(BaseModel):
    id_token: str


class RegistrarRequestSchema(BaseModel):
    codigo_convite: str
    nome: str
    email: EmailStr
    senha: str = Field(min_length=8, max_length=72)
    aceite_termos: bool


class RegistrarVitrineRequestSchema(BaseModel):
    codigo_convite: str
    razao_social: str
    cnpj: str | None = None
    nome_admin: str
    email_admin: EmailStr
    senha_admin: str = Field(min_length=8, max_length=72)
    aceite_termos: bool
    plano_id: int


class TokenResponseSchema(BaseModel):
    access_token: str
    token_type: str = "bearer"
    usuario: UsuarioSchema
    tem_licenca_ativa: bool = True
    checkout_url: str | None = None


class LicencaStatusResponseSchema(BaseModel):
    status: str
