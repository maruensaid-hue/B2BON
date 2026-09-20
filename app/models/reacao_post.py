from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ReacaoPost(Base):
    """Reação em post do Shoal (master prompt §45, Fase 2C) — 1 reação
    por tenant por post; `tipo` (curtir + 8 emojis, ver
    `post_rede_social_service.TIPOS_REACAO_VALIDOS`) substitui/troca a
    reação existente em vez de permitir várias simultâneas do mesmo
    tenant (mesmo espírito de Facebook/LinkedIn — reação é exclusiva
    por post, não um conjunto livre por pessoa como no Slack)."""

    __tablename__ = "reacao_post"
    __table_args__ = (UniqueConstraint("post_id", "tenant_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("post_rede_social.id"), index=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    tipo: Mapped[str] = mapped_column(String, default="curtir")
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
