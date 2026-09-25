from pydantic import BaseModel, ConfigDict


class LinkCapturaLeadSchema(BaseModel):
    """Config do próprio tenant — usada na tela de Configuração para exibir
    o link pronto pra copiar."""

    model_config = ConfigDict(from_attributes=True)

    codigo: str


class InfoCapturaLeadSchema(BaseModel):
    """Info pública mínima pra tela de captura montar o formulário — nunca
    expõe `tenant_id`."""

    nome_exibicao: str


class CriarLeadPublicoRequestSchema(BaseModel):
    nome_empresa: str
    cnpj: str | None = None
    nome_contato: str
    email_contato: str
    telefone_contato: str | None = None
    cargo_contato: str | None = None
