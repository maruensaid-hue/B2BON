from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OfertaSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: str
    icp_id: int | None
    nome: str
    descricao: str
    diferenciais: list
    provas_sociais: list
    faixa_preco_min: float | None
    faixa_preco_max: float | None
    ativo: bool
    criado_em: datetime

    categoria: str | None = None
    problemas_resolvidos: list[str] | None = None
    dores: list[str] | None = None
    casos_uso: list[str] | None = None
    personas: list[str] | None = None
    industrias: list[str] | None = None
    requisitos: list[str] | None = None
    prerequisitos: list[str] | None = None
    incompatibilidades: list[str] | None = None
    objecoes: list[str] | None = None
    cases: list[str] | None = None
    cross_sell: list[str] | None = None
    upsell: list[str] | None = None
    bundles: list[str] | None = None
    perguntas_descoberta: list[str] | None = None
    criterios_qualificacao: list[str] | None = None
    modelo_precificacao: str | None = None
    ticket_medio: float | None = None
    margem_media: float | None = None
    playbook: str | None = None
    disponivel_para_venda: bool = True


class OfertaCreateSchema(BaseModel):
    icp_id: int | None = None
    nome: str
    descricao: str
    diferenciais: list[str] = []
    provas_sociais: list[str] = []
    faixa_preco_min: float | None = None
    faixa_preco_max: float | None = None

    categoria: str | None = None
    problemas_resolvidos: list[str] | None = None
    dores: list[str] | None = None
    casos_uso: list[str] | None = None
    personas: list[str] | None = None
    industrias: list[str] | None = None
    requisitos: list[str] | None = None
    prerequisitos: list[str] | None = None
    incompatibilidades: list[str] | None = None
    objecoes: list[str] | None = None
    cases: list[str] | None = None
    cross_sell: list[str] | None = None
    upsell: list[str] | None = None
    bundles: list[str] | None = None
    perguntas_descoberta: list[str] | None = None
    criterios_qualificacao: list[str] | None = None
    modelo_precificacao: str | None = None
    ticket_medio: float | None = Field(default=None, ge=0)
    margem_media: float | None = Field(default=None, ge=0, le=100)
    playbook: str | None = None
    disponivel_para_venda: bool = True


# Offer Intelligence (§25): na edição só muda o que veio no corpo
# (`exclude_unset`), para a tela antiga não apagar esses campos.
CAMPOS_INTELIGENCIA_OFERTA = tuple(
    nome for nome in OfertaCreateSchema.model_fields if nome not in {
        "icp_id", "nome", "descricao", "diferenciais", "provas_sociais", "faixa_preco_min", "faixa_preco_max"
    }
)


class MaterialOfertaSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    oferta_id: int
    nome_arquivo: str
    tipo_mime: str
    tamanho_bytes: int
    criado_em: datetime
