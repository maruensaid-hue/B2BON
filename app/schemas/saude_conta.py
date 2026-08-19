from datetime import datetime

from pydantic import BaseModel, ConfigDict


class InteracaoContaSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    conta_id: int
    tipo: str
    descricao: str | None
    criado_por_usuario_id: int | None
    criado_em: datetime


class RegistrarInteracaoContaRequestSchema(BaseModel):
    conta_id: int
    tipo: str
    descricao: str | None = None


class ScoreRiscoContaSchema(BaseModel):
    conta_id: int
    score: float
    classificacao: str  # critico | atencao | saudavel
    dias_sem_contato: int | None
    sinais: dict[str, int]


class SaudeContaSchema(BaseModel):
    conta_id: int
    nome: str
    nome_fantasia: str | None
    vendedor_usuario_id: int | None
    vendedor_nome: str | None
    score: float
    classificacao: str
    valor_pipeline_aberto: float


class DashboardSaudeContasSchema(BaseModel):
    score_medio: float | None
    total_contas: int
    criticas: int
    atencao: int
    saudaveis: int
    valor_total_em_risco: float
    roi: float | None
    cs_score: float | None
    nps_medio: float | None


class ScriptResgateContaSchema(BaseModel):
    conta_id: int
    script: str
    justificativa: str


class AtribuirVendedorRequestSchema(BaseModel):
    vendedor_usuario_id: int | None
