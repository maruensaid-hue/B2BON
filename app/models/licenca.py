from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Licenca(Base):
    """Licença de um tenant a um plano — controla franquia/acesso (Onda A)."""

    __tablename__ = "licenca"
    __table_args__ = (UniqueConstraint("tenant_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    plano_id: Mapped[int] = mapped_column(ForeignKey("plano.id"))
    status: Mapped[str] = mapped_column(String)  # ativa | suspensa | expirada
    data_inicio: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    data_expiracao: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
