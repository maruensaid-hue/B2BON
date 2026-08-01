from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Cadencia(Base):
    __tablename__ = "cadencia"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("conta.id"))
    nome: Mapped[str] = mapped_column(String)
    canais: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String)
    data_inicio: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
