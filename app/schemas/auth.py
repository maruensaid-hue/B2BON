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


class TokenResponseSchema(BaseModel):
    access_token: str
    token_type: str = "bearer"
    usuario: UsuarioSchema
