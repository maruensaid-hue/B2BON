from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RegraAutoAprovacao(Base):
    """Auto-aprovação por template — opcional e desligada por padrão (E4-H4)."""

    __tablename__ = "regra_auto_aprovacao"
    __table_args__ = (UniqueConstraint("tenant_id", "template_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    template_id: Mapped[str] = mapped_column(String)
    habilitada: Mapped[bool] = mapped_column(Boolean, default=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
