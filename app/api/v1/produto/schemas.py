"""Schemas da API de produto (Fase 3).

Entidades canônicas de entrada têm `tenant_id` opcional: o valor
enviado é SEMPRE substituído pelo tenant da chave de API.
"""

from pydantic import BaseModel, ConfigDict, Field, create_model

from app.contexts.shared.canonical.commercial import (
    Account,
    CSMetric,
    Customer,
    Interaction,
    Opportunity,
    Organization,
    PipelineStage,
)

PERIODO = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="Mês de referência, formato YYYY-MM.")


def _entrada(entidade):
    return create_model(f"{entidade.__name__}Entrada", __base__=entidade, tenant_id=(str, ""))


OrganizationEntrada = _entrada(Organization)
AccountEntrada = _entrada(Account)
CustomerEntrada = _entrada(Customer)
OpportunityEntrada = _entrada(Opportunity)
PipelineStageEntrada = _entrada(PipelineStage)
InteractionEntrada = _entrada(Interaction)
CSMetricEntrada = _entrada(CSMetric)


class DadosCanonicosMap(BaseModel):
    """Dados de um CRM externo no modelo canônico (ver `docs/b2bon/04_CANONICAL_MODEL.md`)."""

    model_config = ConfigDict(extra="forbid")

    organizations: list[OrganizationEntrada] = Field(default_factory=list, max_length=5000)
    accounts: list[AccountEntrada] = Field(default_factory=list, max_length=5000)
    customers: list[CustomerEntrada] = Field(default_factory=list, max_length=5000)
    opportunities: list[OpportunityEntrada] = Field(default_factory=list, max_length=20000)
    stages: list[PipelineStageEntrada] = Field(default_factory=list, max_length=200)
    interactions: list[InteractionEntrada] = Field(default_factory=list, max_length=50000)
    cs_metrics: list[CSMetricEntrada] = Field(default_factory=list, max_length=20000)
    custo_aquisicao_periodo: float | None = Field(default=None, ge=0, description="Custo total de aquisição no período (para CAC).")


class MapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    periodo: str = PERIODO
    dados: DadosCanonicosMap | None = Field(default=None, description="Sem `dados`, o cálculo usa o CRM da B2B ON do tenant.")
    conexao_id: int | None = Field(default=None, description="Calcula sobre um CRM externo conectado no Integration Hub (Fase 13).")


class MapContasRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conta_ids: list[str] | None = Field(default=None, max_length=1000)
    dados: DadosCanonicosMap | None = None
    conexao_id: int | None = None


class RiscoConta(BaseModel):
    conta_id: str
    nome: str | None = None
    score: float
    classificacao: str
    dias_sem_contato: int
    sinais: dict[str, int]


class MetodologiaMap(BaseModel):
    risco: str = "RULE_BASED_V1"
    descricao: str = (
        "Score de risco por regras explícitas (dias sem contato, reclamações, menção a concorrente, "
        "reunião remarcada, feedback positivo). Não é modelo estatístico nem previsão por IA."
    )


class MapAnaliseResponse(BaseModel):
    fonte: str
    periodo: str
    metodologia: MetodologiaMap = MetodologiaMap()
    economia: dict
    contas: list[RiscoConta]


class ChurnResponse(BaseModel):
    fonte: str
    metodologia: MetodologiaMap = MetodologiaMap()
    previsoes: list[RiscoConta]


class CustomerScoreItem(BaseModel):
    conta_id: str
    cs_score: float | None
    nps_medio: float | None
    saude: float


class CustomerScoreResponse(BaseModel):
    fonte: str
    contas: list[CustomerScoreItem]


class MetricaResponse(BaseModel):
    fonte: str
    periodo: str
    valor: float | None
    detalhe: dict


class EnriquecerEmpresaRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cnpj: str = Field(min_length=14, max_length=18)


class GerarListaApiRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    icp_id: int
    quantidade: int = Field(ge=1, le=500)
