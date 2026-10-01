from typing import Literal

from pydantic import BaseModel, ConfigDict

# Phase I (D-059): FIXED vai para o checkout; STARTING_AT ("a partir de") é venda assistida.
TipoPreco = Literal["FIXED", "STARTING_AT", "CONTRACT"]  # CONTRACT: Government, sempre por contrato (D-072)
Segmento = Literal["PRIVATE", "GOVERNMENT"]
ModeloCobranca = Literal["MONTHLY_SUBSCRIPTION", "GOVERNMENT_LICENSE_PLUS_ANNUAL_SUBSCRIPTION", "GOVERNMENT_ANNUAL_SUBSCRIPTION_ONLY"]


class PlanoSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    franquia_contas_mes: int
    max_usuarios: int | None
    preco_mensal: float
    visivel_self_service: bool
    limite_enriquecimento_site_semanal: int | None
    limite_enriquecimento_contatos_semanal: int | None
    limite_cadencias_mes: int | None
    limite_campanhas_mes: int | None
    permite_ab_teste_cadencia: bool
    permite_auto_aprovacao: bool
    permite_webhook_relatorio: bool
    permite_api_parceiros: bool
    permite_subtenants: bool
    permite_registro_oportunidade: bool
    retencao_dias_relatorio: int | None
    retencao_dias_auditoria: int | None
    modulos_contratados: list[str]
    categoria: str
    tipo_preco: str
    segmento: str = "PRIVATE"
    modelo_cobranca: str = "MONTHLY_SUBSCRIPTION"
    preco_licenca: float | None = None
    preco_implantacao: float | None = None
    preco_assinatura_anual: float | None = None
    creditos_ia_anuais: int | None = None
    recomendado: bool = False
    entitlements: dict | None = None


class CriarPlanoRequestSchema(BaseModel):
    nome: str
    franquia_contas_mes: int
    max_usuarios: int | None = None
    preco_mensal: float
    visivel_self_service: bool = True
    limite_enriquecimento_site_semanal: int | None = None
    limite_enriquecimento_contatos_semanal: int | None = None
    limite_cadencias_mes: int | None = None
    limite_campanhas_mes: int | None = None
    permite_ab_teste_cadencia: bool = False
    permite_auto_aprovacao: bool = False
    permite_webhook_relatorio: bool = False
    permite_api_parceiros: bool = False
    permite_subtenants: bool = False
    permite_registro_oportunidade: bool = False
    retencao_dias_relatorio: int | None = None
    retencao_dias_auditoria: int | None = None
    modulos_contratados: list[str] = ["map", "predator", "crm"]
    categoria: str = "suite"
    tipo_preco: TipoPreco = "FIXED"
    segmento: Segmento = "PRIVATE"
    modelo_cobranca: ModeloCobranca = "MONTHLY_SUBSCRIPTION"
    preco_licenca: float | None = None
    preco_implantacao: float | None = None
    preco_assinatura_anual: float | None = None
    creditos_ia_anuais: int | None = None
    recomendado: bool = False
    entitlements: dict | None = None
    motivo: str | None = None  # registrado na auditoria (mudança de preço/condição)


class AtualizarPlanoRequestSchema(CriarPlanoRequestSchema):
    pass
