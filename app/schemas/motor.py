from datetime import datetime

from pydantic import BaseModel, ConfigDict


class InteracaoTenantSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    tipo: str
    descricao: str | None
    criado_por_usuario_id: int | None
    criado_em: datetime


class RegistrarInteracaoRequestSchema(BaseModel):
    tenant_id: str
    tipo: str
    descricao: str | None = None


class ScoreRiscoSchema(BaseModel):
    tenant_id: str
    score: float
    classificacao: str  # critico | atencao | saudavel
    dias_sem_contato: int | None
    sinais: dict[str, int]


class SaudeTenantSchema(BaseModel):
    tenant_id: str
    nome_exibicao: str
    score: float
    classificacao: str
    meses_como_cliente: float
    valor_mensal: float
    valor_em_risco: float


class DashboardMotorSchema(BaseModel):
    score_medio: float | None
    total_tenants: int
    criticos: int
    atencao: int
    saudaveis: int
    valor_total_em_risco: float


class ScriptResgateSchema(BaseModel):
    tenant_id: str
    script: str
    justificativa: str
