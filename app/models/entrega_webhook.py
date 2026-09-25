from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EntregaWebhook(Base):
    """Uma entrega de um evento de domínio a uma assinatura (Fase 3).
    Única por (assinatura, evento): reprocessar o outbox não duplica."""

    __tablename__ = "entrega_webhook"
    __table_args__ = (UniqueConstraint("assinatura_id", "evento_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assinatura_id: Mapped[int] = mapped_column(ForeignKey("assinatura_webhook_tenant.id"), index=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    evento_id: Mapped[str] = mapped_column(String)
    tipo: Mapped[str] = mapped_column(String)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String, default="pendente")  # pendente | entregue | desistida
    tentativas: Mapped[int] = mapped_column(Integer, default=0)
    proxima_tentativa_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ultimo_status_http: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ultimo_erro: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    entregue_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
