from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ProvisionarTenantRequestSchema(BaseModel):
    tenant_id: str
    razao_social: str
    cnpj: str | None = None
    plano_id: int
    nome_admin: str
    email_admin: EmailStr
    senha_admin: str = Field(min_length=8, max_length=72)


class CriarChaveApiRequestSchema(BaseModel):
    nome: str


class ChaveApiCriadaSchema(BaseModel):
    """Única resposta em que `chave` (o segredo completo) aparece — depois
    disso só existe o hash no banco, não tem como recuperar."""

    id: int
    nome: str
    prefixo: str
    chave: str
    criado_em: datetime


class ChaveApiSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    prefixo: str
    criado_em: datetime
    ultimo_uso_em: datetime | None
    revogada_em: datetime | None


class AssinaturaWebhookRequestSchema(BaseModel):
    url_callback: str


class AssinaturaWebhookCriadaSchema(BaseModel):
    """`segredo` só aparece aqui — usado pelo Distribuidor pra verificar
    `X-B2BON-Signature` em cada evento recebido."""

    url_callback: str
    segredo: str
    ativa: bool


class AssinaturaWebhookSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    url_callback: str
    ativa: bool
    criado_em: datetime
