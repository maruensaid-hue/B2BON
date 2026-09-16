from datetime import datetime

from pydantic import BaseModel


class SaudeCanalEmailSchema(BaseModel):
    canal: str
    enviados: int
    bounces: int
    spam_reports: int
    taxa_bounce: float
    taxa_spam: float
    pausado: bool
    limiar_bounce: float
    limiar_spam: float


class ContatoComBounceSchema(BaseModel):
    decisor_id: int | None
    conta_id: int | None
    nome: str
    email: str | None
    conta_nome: str | None
    canal: str  # "email" (cadência) ou "campanha"
    motivo_bounce: str | None
    bounce_em: datetime


class RelatorioEntregaSchema(BaseModel):
    """Raio-X 2026-09-16 — combina o que já existia disperso (saúde do
    canal de e-mail, taxa de abertura, taxa de resposta por canal) com a
    lista de contatos que efetivamente causaram bounce, antes só um
    contador agregado sem saber quem."""

    saude_email: SaudeCanalEmailSchema
    taxa_abertura_email: float | None
    taxa_resposta_por_canal: dict[str, float]
    contatos_com_bounce: list[ContatoComBounceSchema]
