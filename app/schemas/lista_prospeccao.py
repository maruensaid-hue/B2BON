from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ListaProspeccaoSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    nome: str
    icp_id: int | None
    cargos_alvo: list[str] | None
    criado_em: datetime


class ListaProspeccaoCreateSchema(BaseModel):
    nome: str
    icp_id: int | None = None
    cargos_alvo: list[str] | None = None


class ContaBloqueadaSchema(BaseModel):
    conta_id: int
    nome: str
    motivo: str


class ExcluirContasResponseSchema(BaseModel):
    apagadas: int
    bloqueadas: int
    detalhes_bloqueadas: list[ContaBloqueadaSchema]


class ElegibilidadeContaSchema(BaseModel):
    conta_id: int
    nome: str
    bloqueada: bool
    motivo: str | None


class ExcluirContasRequestSchema(BaseModel):
    """Seleção manual opcional (caixas de seleção no frontend) — quando
    omitido/`None`, tenta apagar todas as contas visíveis no escopo (todos
    os leads, ou todas as contas da lista)."""

    conta_ids: list[int] | None = None


class PreviaLimpezaLeadsSchema(BaseModel):
    total: int
    serao_apagadas: int
    protegidas: int
