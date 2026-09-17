from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NotificacaoRedeSocial(Base):
    """Notificação da Rede Social (master prompt §65, Fase 2D) — buscada
    por polling (sem WebSocket/SSE, infra de tempo real fora de escopo
    desta fase)."""

    __tablename__ = "notificacao_rede_social"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    tipo: Mapped[str] = mapped_column(String)
    referencia_tipo: Mapped[str] = mapped_column(String)
    referencia_id: Mapped[int] = mapped_column(Integer)
    mensagem: Mapped[str] = mapped_column(String)
    lida_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
