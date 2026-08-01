from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DescarteConta(Base):
    """Histórico de descartes — insumo do refinamento do score de aderência (E2-H4)."""

    __tablename__ = "descarte_conta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("conta.id"))
    motivo: Mapped[str] = mapped_column(String)
    cnae: Mapped[str | None] = mapped_column(String, nullable=True)
    porte: Mapped[str | None] = mapped_column(String, nullable=True)
    uf: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
