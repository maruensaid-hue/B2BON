from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RegistroOportunidadeSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    vendedor_usuario_id: int
    cnpj: str
    nome_empresa: str
    conta_id: int | None
    status: str
    criado_em: datetime
    expira_em: datetime


class RegistrarOportunidadeRequestSchema(BaseModel):
    cnpj: str
    nome_empresa: str
    conta_id: int | None = None


class AtualizarStatusRegistroRequestSchema(BaseModel):
    status: str  # ganho | perdido | cancelado


class SolicitacaoDescontoSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    registro_oportunidade_id: int
    solicitante_usuario_id: int
    percentual_solicitado: float
    justificativa: str | None
    status: str
    aprovador_usuario_id: int | None
    motivo_decisao: str | None
    criado_em: datetime
    decidido_em: datetime | None


class SolicitarDescontoRequestSchema(BaseModel):
    percentual_solicitado: float
    justificativa: str | None = None


class DecidirSolicitacaoDescontoRequestSchema(BaseModel):
    aprovar: bool
    motivo: str | None = None
