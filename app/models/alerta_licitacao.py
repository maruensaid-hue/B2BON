from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RegraAlertaLicitacao(Base):
    """Regra de alerta de licitações do tenant (V5.2.1, Fase 4). Critérios explícitos e auditáveis; privada do tenant.

    `icp_id` (opcional) liga a regra a um ICP: sem UFs próprias, a regra herda as UFs do ICP. Não há inferência por IA: a correspondência é
    determinística (palavras do objeto, UF, valor, modalidade, prazo) e cada alerta guarda os fatores que o produziram."""

    __tablename__ = "regra_alerta_licitacao"
    __table_args__ = (UniqueConstraint("tenant_id", "nome", name="uq_regra_alerta_licitacao_tenant_nome"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    nome: Mapped[str] = mapped_column(String)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)
    icp_id: Mapped[int | None] = mapped_column(ForeignKey("icp.id"), nullable=True)
    palavras_chave: Mapped[list] = mapped_column(JSON, default=list)
    palavras_excluir: Mapped[list] = mapped_column(JSON, default=list)
    ufs: Mapped[list] = mapped_column(JSON, default=list)
    modalidades: Mapped[list] = mapped_column(JSON, default=list)
    valor_minimo: Mapped[float | None] = mapped_column(Float, nullable=True)
    valor_maximo: Mapped[float | None] = mapped_column(Float, nullable=True)
    dias_minimos_prazo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usar_portfolio: Mapped[bool] = mapped_column(Boolean, default=False)  # soma ao critério as palavras do nome da oferta ativa
    relevancia_minima: Mapped[int] = mapped_column(Integer, default=40)
    frequencia: Mapped[str] = mapped_column(String, default="diaria")  # imediata | diaria
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class AlertaLicitacao(Base):
    """Um alerta por (tenant, edital do corpus), mesmo que várias regras casem (guarda a melhor pontuação e a lista de regras)."""

    __tablename__ = "alerta_licitacao"
    __table_args__ = (UniqueConstraint("tenant_id", "corpus_id", name="uq_alerta_licitacao_tenant_corpus"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    corpus_id: Mapped[int] = mapped_column(ForeignKey("licitacao_publica.id"), index=True)
    score: Mapped[int] = mapped_column(Integer)
    fatores: Mapped[list] = mapped_column(JSON, default=list)  # [{fator, pontos, detalhe}]
    regras: Mapped[list] = mapped_column(JSON, default=list)  # [{id, nome, frequencia}]
    motivo: Mapped[str] = mapped_column(String, default="nova")  # nova | atualizada
    estado: Mapped[str] = mapped_column(String, default="novo", index=True)  # novo | visto | dispensado | acompanhado
    versao_corpus: Mapped[int] = mapped_column(Integer, default=1)  # versão do fato público quando o alerta foi gerado/atualizado
    situacao_externa: Mapped[str | None] = mapped_column(String, nullable=True)
    atualizacao_nao_vista: Mapped[bool] = mapped_column(Boolean, default=False)
    entrega_estado: Mapped[str] = mapped_column(String, default="pendente")  # pendente | enviada | falhou | desistida | desligada | sem_destinatario
    entrega_tentativas: Mapped[int] = mapped_column(Integer, default=0)
    entrega_ultimo_erro: Mapped[str | None] = mapped_column(Text, nullable=True)
    entregue_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    visto_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class EstadoAlertasLicitacao(Base):
    """Cursor por tenant sobre o feed de eventos do corpus (`evento_licitacao_publica.id`) e controle do resumo diário."""

    __tablename__ = "estado_alertas_licitacao"

    tenant_id: Mapped[str] = mapped_column(String, primary_key=True)
    ultimo_evento_id: Mapped[int] = mapped_column(Integer, default=0)
    avaliado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ultimo_resumo_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
