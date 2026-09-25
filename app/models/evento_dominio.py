from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EventoDominio(Base):
    """Outbox de eventos de domínio (Fase 2, Master Prompt §77).

    Gravado na MESMA transação da mudança de negócio que o originou
    (`app.contexts.shared.events.publicar`), então evento e dado nunca
    divergem. Consumidores (webhooks, integrações, Intelligence) leem por
    `processado_em IS NULL` via `processar_pendentes`, nunca no caminho
    da requisição."""

    __tablename__ = "evento_dominio"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    evento_id: Mapped[str] = mapped_column(String, unique=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    tipo: Mapped[str] = mapped_column(String, index=True)
    versao: Mapped[int] = mapped_column(Integer, default=1)
    agregado_tipo: Mapped[str] = mapped_column(String)
    agregado_id: Mapped[str] = mapped_column(String)
    ator_id: Mapped[str | None] = mapped_column(String, nullable=True)
    classificacao: Mapped[str] = mapped_column(String, default="INTERNAL")
    correlation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    ocorrido_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    processado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    tentativas: Mapped[int] = mapped_column(Integer, default=0)
    ultimo_erro: Mapped[str | None] = mapped_column(String, nullable=True)
