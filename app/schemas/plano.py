from pydantic import BaseModel, ConfigDict


class PlanoSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nome: str
    franquia_contas_mes: int
    max_usuarios: int
    preco_mensal: float
    visivel_self_service: bool
    limite_enriquecimento_site_semanal: int | None
    limite_enriquecimento_contatos_semanal: int | None
    permite_ab_teste_cadencia: bool
    permite_auto_aprovacao: bool
    permite_webhook_relatorio: bool
    permite_api_parceiros: bool
    permite_subtenants: bool
    retencao_dias_relatorio: int | None
    retencao_dias_auditoria: int | None


class CriarPlanoRequestSchema(BaseModel):
    nome: str
    franquia_contas_mes: int
    max_usuarios: int
    preco_mensal: float
    visivel_self_service: bool = True
    limite_enriquecimento_site_semanal: int | None = None
    limite_enriquecimento_contatos_semanal: int | None = None
    permite_ab_teste_cadencia: bool = False
    permite_auto_aprovacao: bool = False
    permite_webhook_relatorio: bool = False
    permite_api_parceiros: bool = False
    permite_subtenants: bool = False
    retencao_dias_relatorio: int | None = None
    retencao_dias_auditoria: int | None = None


class AtualizarPlanoRequestSchema(CriarPlanoRequestSchema):
    pass
