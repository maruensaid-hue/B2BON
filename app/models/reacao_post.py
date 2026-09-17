from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReacaoPost(Base):
    """Reação em post da Rede Social (master prompt §45, Fase 2C) —
    tipo único ("curtir"), toggle: 1 reação por tenant por post, sem
    enum de emoji (YAGNI até haver demanda de reações variadas)."""

    __tablename__ = "reacao_post"
    __table_args__ = (UniqueConstraint("post_id", "tenant_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("post_rede_social.id"), index=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
