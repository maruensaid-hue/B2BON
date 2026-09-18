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


class PerformanceIaSchema(BaseModel):
    total_propostas: int
    mensagens_editadas: int
    aprovacoes_rejeitadas: int
    mensagens_enviadas: int
    respostas_detectadas: int
    taxa_aceitacao: float
    taxa_edicao: float
    taxa_rejeicao: float
    taxa_resposta: float


class PadroesObservadosSchema(BaseModel):
    ticket_medio: float | None
    amostra_ticket_medio: int
    ciclo_medio_dias: float | None
    amostra_ciclo_medio: int
    motivo_perda_mais_comum: str | None
    motivo_perda_mais_comum_contagem: int
    amostra_motivo_perda: int
    taxa_ganho_com_decision_maker: float | None
    taxa_ganho_sem_decision_maker: float | None
    amostra_decision_maker: int
