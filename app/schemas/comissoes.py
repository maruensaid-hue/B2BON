from datetime import date

from pydantic import BaseModel, Field


class ComponenteTributoSchema(BaseModel):
    nome: str = Field(min_length=1)
    aliquota: float = Field(ge=0, lt=1)


class PerfilTributarioSchema(BaseModel):
    regime: str = Field(min_length=1)  # ex.: LUCRO_PRESUMIDO
    vigente_de: date
    vigente_ate: date | None = None
    tipo_receita: str = "*"
    municipio: str | None = None
    componentes: list[ComponenteTributoSchema]
    aliquota_efetiva: float | None = Field(default=None, ge=0, lt=1)  # vazio = soma dos componentes
    metodo_calculo: str | None = None
    fonte: str | None = None
    observacoes: str | None = None


class ModeloCustoInfraSchema(BaseModel):
    nome: str = Field(min_length=1)
    vigente_de: date
    vigente_ate: date | None = None
    componentes: list[dict]
    fonte: str | None = None
    observacoes: str | None = None


class RecalculoSchema(BaseModel):
    motivo: str = Field(min_length=1)
