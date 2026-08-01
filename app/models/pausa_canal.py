from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PausaCanal(Base):
    """Pausa automática de canal por degradação de reputação (E10-H2)."""

    __tablename__ = "pausa_canal"
    __table_args__ = (UniqueConstraint("tenant_id", "canal"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    canal: Mapped[str] = mapped_column(String)
    ativa: Mapped[bool] = mapped_column(Boolean, default=False)
    motivo: Mapped[str | None] = mapped_column(String, nullable=True)
    pausado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
