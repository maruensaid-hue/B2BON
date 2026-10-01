from datetime import date, datetime

from pydantic import BaseModel, Field


class PerfilTributarioSchema(BaseModel):
    regime: str = Field(min_length=1)  # ex.: LUCRO_PRESUMIDO
    vigente_de: date
    vigente_ate: date | None = None
    tipo_receita: str = "*"
    municipio: str | None = None
    item_lista_servico: str | None = None  # LC 116 (ex.: 1.05)
    codigo_servico: str | None = None  # código de serviço municipal (ex.: 2800)
    versao_legal: str | None = None
    # Um por tributo (D-075): {"tributo": "IRPJ", "base": "PRESUNCAO", "aliquota": 0.15, "presuncao": 0.32}, validados no Tax Engine
    componentes: list[dict]
    metodo_calculo: str | None = None
    fonte: str | None = None
    observacoes: str | None = None


class ComponenteInfraSchema(BaseModel):
    """Fornecedor/plano do Infrastructure Cost Pool (D-076). Custos no ciclo de cobrança e na moeda informados."""

    fornecedor: str = Field(min_length=1)
    servico: str = Field(min_length=1)
    categoria: str
    plano: str | None = None
    plano_referencia: str | None = None
    ciclo_cobranca: str = "MONTHLY"
    moeda: str = "BRL"
    custo_contratado: float | None = None
    custo_referencia: float | None = None
    custo_real: float | None = None
    capacidade_contratada: float | None = None
    uso_atual: float | None = None
    unidade_uso: str | None = None
    politica_custo: str = "MAX_CONTRACTED_PLAN"
    metodo_alocacao: str = "WEIGHTED"
    contabilizacao: str = "INFRASTRUCTURE"
    vigente_de: date
    vigente_ate: date | None = None
    observacoes: str | None = None


class AtualizarComponenteInfraSchema(BaseModel):
    dados: dict
    motivo: str = Field(min_length=1)


class UsoCapacidadeSchema(BaseModel):
    uso: float = Field(ge=0)
    fonte: str | None = None
    medido_em: datetime | None = None


class CustoDiretoSchema(BaseModel):
    componente_id: int
    tenant_id: str
    competencia: str  # AAAA-MM
    custo: float = Field(ge=0)
    quantidade: float | None = None
    fonte: str | None = None


class DecisaoAlertaSchema(BaseModel):
    decisao: str = Field(min_length=1)


class PoliticaInfraSchema(BaseModel):
    pesos: dict[str, float]
    limiares: dict[str, float]
    custo_comissao: str = "PROVISIONED"
    motivo: str = Field(min_length=1)


class RecalculoSchema(BaseModel):
    motivo: str = Field(min_length=1)


class CotacaoCambioSchema(BaseModel):
    moeda_base: str = "USD"
    moeda_cotacao: str = "BRL"
    taxa: float = Field(gt=0)
    fonte: str = Field(min_length=1)
    vigente_em: datetime | None = None


class PoliticaMargemSchema(BaseModel):
    deduzir_custo_ia: bool
    motivo: str = Field(min_length=1)
