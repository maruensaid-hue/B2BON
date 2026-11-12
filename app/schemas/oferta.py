from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.oferta_seo import (
    LIMITE_PALAVRAS_CHAVE,
    TAMANHO_MAXIMO_PALAVRA_CHAVE,
    TAMANHO_MAXIMO_SEO_DESCRICAO,
    TAMANHO_MAXIMO_SEO_TITULO,
    normalizar_palavras_chave,
)


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
    palavras_chave: list[str] | None = None
    seo_titulo: str | None = None
    seo_descricao: str | None = None
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
    # SEO e palavras-chave entram no texto das mensagens como vocabulário (ver `app/services/oferta_seo.py`).
    palavras_chave: list[str] | None = None
    seo_titulo: str | None = None
    seo_descricao: str | None = None
    disponivel_para_venda: bool = True

    @field_validator("palavras_chave")
    @classmethod
    def _palavras_chave(cls, valores: list[str] | None) -> list[str] | None:
        if valores is None:
            return None
        limpas = normalizar_palavras_chave(valores)
        if len(limpas) > LIMITE_PALAVRAS_CHAVE:
            raise ValueError(f"Use no máximo {LIMITE_PALAVRAS_CHAVE} palavras-chave: poucas e específicas orientam melhor a mensagem.")
        longa = next((p for p in limpas if len(p) > TAMANHO_MAXIMO_PALAVRA_CHAVE), None)
        if longa is not None:
            raise ValueError(f"Cada palavra-chave pode ter até {TAMANHO_MAXIMO_PALAVRA_CHAVE} caracteres (\"{longa[:30]}...\" passou).")
        return limpas

    @field_validator("seo_titulo", "seo_descricao")
    @classmethod
    def _texto_seo(cls, valor: str | None, info) -> str | None:
        texto = (valor or "").strip()
        limite = TAMANHO_MAXIMO_SEO_TITULO if info.field_name == "seo_titulo" else TAMANHO_MAXIMO_SEO_DESCRICAO
        if len(texto) > limite:
            rotulo = "O título SEO" if info.field_name == "seo_titulo" else "A descrição SEO"
            raise ValueError(f"{rotulo} pode ter até {limite} caracteres (tem {len(texto)}).")
        return texto or None


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
