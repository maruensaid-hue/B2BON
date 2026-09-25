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
    negocio_id_gerado: int | None = None
    destino_conversao: str | None = None
    criado_em: datetime


class ConversaoSinalSchema(BaseModel):
    conta_id: int
    negocio_id: int | None = None
    destino: str = "crm"
    conta_reaproveitada: bool = False
    negocio_reaproveitado: bool = False
    sinais_fechados: list[int] = []


class SaudeRelacionamentoSchema(BaseModel):
    tenant_id_alvo: str
    empresa_nome: str
    dias_sem_interacao: int | None
    tem_relacionamento_declarado: bool
    classificacao: str
    sugestoes: list[str]
    # Relationship Intelligence (Fase 8)
    forca: str = "NENHUMA"
    motivos: list[str] = []
    conectadas: bool = False
    relacionamentos: list[dict] = []


class RiscoPipelineSchema(BaseModel):
    negocio_id: int
    negocio_nome: str
    conta_id: int
    conta_nome: str | None
    dias_sem_atividade: int
    tem_decision_maker: bool
    riscos: list[str]


class AtribuicaoReceitaSchema(BaseModel):
    contas_geradas_pela_rede: int
    negocios_em_aberto_valor: float
    negocios_ganhos_valor: float
    sinais_gerados: int
    sinais_convertidos: int
    taxa_conversao_sinais: float


class SugestaoExpansaoSchema(BaseModel):
    conta_id: int
    conta_nome: str
    oferta_id: int
    oferta_nome: str
    motivo: str
