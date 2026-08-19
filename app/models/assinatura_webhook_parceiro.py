from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AssinaturaWebhookParceiro(Base):
    """Callback de saída do Distribuidor (Fase 2 da hierarquia, raio-X) —
    uma por tenant (`UniqueConstraint`, registrar de novo substitui a
    anterior). `segredo` assina cada evento via HMAC-SHA256
    (`X-B2BON-Signature`) — só existe completo na resposta de criação,
    igual à chave de API."""

    __tablename__ = "assinatura_webhook_parceiro"
    __table_args__ = (UniqueConstraint("tenant_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    url_callback: Mapped[str] = mapped_column(String)
    segredo: Mapped[str] = mapped_column(String)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
