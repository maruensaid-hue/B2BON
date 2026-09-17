from datetime import datetime

from pydantic import BaseModel


class FitIcpRedeSchema(BaseModel):
    tenant_id_candidato: str
    empresa_nome: str
    fit_score: float
    matched_icp: str
    reasons: list[str]
    missing_data: list[str]
    confidence: str


class MatchIntentSchema(BaseModel):
    tenant_id_candidato: str
    empresa_nome: str
    match_score: float
    match_reasons: list[str]
    confidence: str
    signals: list[str]


class ExplicacaoMatchSchema(BaseModel):
    explicacao: str


class SinalOportunidadeSchema(BaseModel):
    id: int
    tenant_id_alvo: str
    empresa_nome: str
    tipo_sinal: str
    score: float
    confianca: str
    motivo: str
    evidencias: list[str]
    status: str
    conta_id_gerada: int | None
    criado_em: datetime


class ConversaoSinalSchema(BaseModel):
    conta_id: int


class SaudeRelacionamentoSchema(BaseModel):
    tenant_id_alvo: str
    empresa_nome: str
    dias_sem_interacao: int | None
    tem_relacionamento_declarado: bool
    classificacao: str
    sugestoes: list[str]
