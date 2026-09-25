from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class UnidadeCompras(Base):
    """Procurement Unit (§37).

    Dado CONFIDENTIAL do tenant comprador (barreira Buy/Sell, Fase 10)."""

    __tablename__ = "unidade_compras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    orgao_id: Mapped[int] = mapped_column(ForeignKey("orgao_publico.id"), index=True)
    nome: Mapped[str] = mapped_column(String)
    codigo: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
