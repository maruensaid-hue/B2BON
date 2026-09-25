from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.crypto import TextoCriptografado
from app.db.base import Base


class AssinaturaWebhookTenant(Base):
    """Webhook de saída do tenant para eventos de domínio (Fase 3).

    `segredo` assina cada entrega (HMAC-SHA256) e precisa ser recuperável
    para assinar — por isso fica criptografado em repouso
    (`TextoCriptografado`), não em hash."""

    __tablename__ = "assinatura_webhook_tenant"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    url: Mapped[str] = mapped_column(String)
    eventos: Mapped[list] = mapped_column(JSON, default=list)
    segredo: Mapped[str] = mapped_column(TextoCriptografado)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
