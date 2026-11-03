from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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
    criterios_sinais: list = []
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
    criterios_sinais: list[dict] = []


class ICPPerformanceItemSchema(BaseModel):
    icp_id: int
    nome: str
    versao: int
    total_contas: int
    score_medio: float | None
    contas_por_status: dict[str, int]


class SinalCatalogoSchema(BaseModel):
    codigo: str
    rotulo: str
    tipo: str
    fonte: str
    na_mensagem: bool
    descricao: str


class CoorteRequestSchema(BaseModel):
    criterios: list[dict] = []
    icp_id: int | None = None
    limite: int = Field(default=50, ge=1, le=500)


class CoorteContaSchema(BaseModel):
    conta_id: int
    nome: str
    motivos: list[str]


class CoorteSchema(BaseModel):
    total: int
    avaliadas: int
    contas: list[CoorteContaSchema]
