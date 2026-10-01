from datetime import date, datetime

from pydantic import BaseModel, Field


class PerfilTributarioSchema(BaseModel):
    regime: str = Field(min_length=1)  # ex.: LUCRO_PRESUMIDO
    vigente_de: date
    vigente_ate: date | None = None
    tipo_receita: str = "*"
    municipio: str | None = None
    codigo_servico: str | None = None
    # Um por tributo (D-075): {"tributo": "IRPJ", "base": "PRESUNCAO", "aliquota": 0.15, "presuncao": 0.32}, validados no Tax Engine
    componentes: list[dict]
    metodo_calculo: str | None = None
    fonte: str | None = None
    observacoes: str | None = None


class ModeloCustoInfraSchema(BaseModel):
    nome: str = Field(min_length=1)
    vigente_de: date
    vigente_ate: date | None = None
    componentes: list[dict]  # {"categoria": "cloud_cost", "metodo": "PERCENTAGE", "percentual": 0.04}
    fonte: str | None = None
    observacoes: str | None = None


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
