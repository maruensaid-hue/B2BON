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
    amostra_minima: int
    # False com conta SMTP própria: o provedor não devolve bounce/spam, então as taxas em zero não provam nada.
    medido_pelo_provedor: bool = True


class ContatoComBounceSchema(BaseModel):
    decisor_id: int | None
    conta_id: int | None
    nome: str
    email: str | None
    conta_nome: str | None
    canal: str  # "email" (cadência) ou "campanha"
    motivo_bounce: str | None
    bounce_em: datetime


class RegistrarBouncesManuaisRequestSchema(BaseModel):
    texto: str


class RegistroBouncesManuaisSchema(BaseModel):
    registrados: list[str]
    ja_registrados: list[str]
    nao_encontrados: list[str]


class ResumoEnviosSchema(BaseModel):
    enviados: int = 0
    erros: int = 0
    nao_enviados: int = 0
    pendentes: int = 0


class RelatorioEntregaSchema(BaseModel):
    """Raio-X 2026-09-16 — combina o que já existia disperso (saúde do
    canal de e-mail, taxa de abertura, taxa de resposta por canal) com a
    lista de contatos que efetivamente causaram bounce, antes só um
    contador agregado sem saber quem."""

    resumo_envios: ResumoEnviosSchema = ResumoEnviosSchema()
    saude_email: SaudeCanalEmailSchema
    taxa_abertura_email: float | None
    taxa_resposta_por_canal: dict[str, float]
    contatos_com_bounce: list[ContatoComBounceSchema]


class EnvioEmailSchema(BaseModel):
    origem: str  # "cadencia" | "campanha"
    origem_nome: str
    decisor_id: int | None
    conta_id: int | None
    nome: str
    email: str | None
    conta_nome: str | None
    status: str  # erro | enviado | aberto | pendente | nao_enviado | cancelado
    detalhe: str | None
    enviado_em: datetime | None
    criado_em: datetime


class ListaEnviosEmailSchema(BaseModel):
    """Raio-X 2026-09-17 — visão granular por destinatário, distinta do
    `saude_email` agregado (que só conta confirmação "delivered" já
    recebida via webhook do SendGrid)."""

    itens: list[EnvioEmailSchema]
    total: int
    contagem_por_status: dict[str, int]
