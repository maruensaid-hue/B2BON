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
