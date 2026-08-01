from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ICPSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    grupo_id: str
    clonado_de_id: int | None
    nome: str
    versao: int
    ativo: bool
    segmento: str
    porte: str
    regiao: str
    dores: list
    gatilhos: list
    cnae_codigos: list
    ufs: list
    criado_em: datetime
    atualizado_em: datetime


class ICPCreateSchema(BaseModel):
    nome: str
    segmento: str
    porte: str
    regiao: str
    dores: list[str] = []
    gatilhos: list[str] = []
    cnae_codigos: list[str] = []
    ufs: list[str] = []


class ICPPerformanceItemSchema(BaseModel):
    icp_id: int
    nome: str
    versao: int
    total_contas: int
    score_medio: float | None
    contas_por_status: dict[str, int]
