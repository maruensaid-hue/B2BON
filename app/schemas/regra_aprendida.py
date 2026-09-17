from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RegraAprendidaCreateSchema(BaseModel):
    icp_id: int | None = None
    oferta_id: int | None = None
    canal: str | None = None
    regra: str


class RegraAprendidaSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    icp_id: int | None
    oferta_id: int | None
    canal: str | None
    regra: str
    ativa: bool
    criado_em: datetime


class CorrecaoRecenteSchema(BaseModel):
    id: int
    tipo: str  # "edicao" | "rejeicao"
    conta_nome: str | None
    canal: str | None
    icp_id: int | None
    oferta_id: int | None
    conteudo_anterior: str | None
    conteudo_novo: str | None
    motivo: str | None
    criado_em: datetime


class SugestaoRegraSchema(BaseModel):
    regra_sugerida: str
