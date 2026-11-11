from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

FormaPagamento = Literal["pix", "boleto", "cartao_credito", "cartao_debito"]
Formato = Literal["presencial", "online"]


class ConfiguracaoPreReservaSchema(BaseModel):
    """Configuração do formulário, como o próprio tenant edita na tela de Configuração."""

    model_config = ConfigDict(from_attributes=True)

    ativo: bool = True
    marca: str = Field(min_length=1, max_length=120)
    titulo: str = Field(min_length=1, max_length=160)
    descricao: str | None = Field(default=None, max_length=4000)
    site: str | None = Field(default=None, max_length=200)
    datas_disponiveis: list[date] = Field(default_factory=list, max_length=400)
    antecedencia_minima_dias: int = Field(default=10, ge=0, le=365)
    horas_pre_reserva: int = Field(default=48, ge=1, le=720)
    valor_presencial: float | None = Field(default=None, ge=0)
    valor_online: float | None = Field(default=None, ge=0)
    percentual_sinal: int = Field(default=50, ge=0, le=100)
    formas_pagamento: list[FormaPagamento] = Field(default_factory=lambda: ["pix", "boleto", "cartao_credito", "cartao_debito"])
    condicao_especial: str | None = Field(default=None, max_length=1000)


class InfoPublicaPreReservaSchema(BaseModel):
    """O que a página pública mostra — nunca expõe `tenant_id` nem quem já reservou o quê, só as datas que ainda estão livres."""

    marca: str
    titulo: str
    descricao: str | None
    site: str | None
    datas_livres: list[date]
    antecedencia_minima_dias: int
    horas_pre_reserva: int
    valor_presencial: float | None
    valor_online: float | None
    percentual_sinal: int
    formas_pagamento: list[str]
    condicao_especial: str | None


class CriarPreReservaRequestSchema(BaseModel):
    data_evento: date
    formato: Formato
    cidade: str | None = Field(default=None, max_length=120)
    participantes: int | None = Field(default=None, ge=1, le=100000)
    forma_pagamento: FormaPagamento
    nome_empresa: str = Field(min_length=1, max_length=200)
    cnpj: str | None = Field(default=None, max_length=20)
    nome_contato: str = Field(min_length=1, max_length=160)
    cargo_contato: str | None = Field(default=None, max_length=120)
    email_contato: str = Field(min_length=3, max_length=200)
    telefone_contato: str = Field(min_length=8, max_length=30)
    observacoes: str | None = Field(default=None, max_length=2000)
    aceite_contato: bool


class PreReservaCriadaSchema(BaseModel):
    data_evento: date
    expira_em: datetime
    valor: float
    valor_sinal: float


class PreReservaSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conta_id: int
    negocio_id: int
    nome_empresa: str
    nome_contato: str
    data_evento: date
    formato: str
    cidade: str | None
    participantes: int | None
    forma_pagamento: str | None
    observacoes: str | None
    valor: float
    status: str
    expira_em: datetime
    criado_em: datetime


class AlterarStatusPreReservaSchema(BaseModel):
    status: Literal["confirmada", "cancelada"]
