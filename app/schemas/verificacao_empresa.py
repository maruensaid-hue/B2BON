from datetime import datetime

from pydantic import BaseModel, ConfigDict


class VerificacaoEmpresaSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    status: str
    email_verificacao: str
    dominio_confere: bool
    cnpj_encontrado_receita: bool
    solicitado_em: datetime
    revisado_em: datetime | None
    motivo_rejeicao: str | None


class SolicitarVerificacaoRequestSchema(BaseModel):
    email_verificacao: str


class RevisarVerificacaoRequestSchema(BaseModel):
    aprovar: bool
    motivo_rejeicao: str | None = None
