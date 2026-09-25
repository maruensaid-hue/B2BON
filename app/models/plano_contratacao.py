from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PlanoContratacao(Base):
    """Procurement Plan / PCA (§39).

    Dado CONFIDENTIAL do tenant comprador (barreira Buy/Sell, Fase 10)."""

    __tablename__ = "plano_contratacao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    orgao_id: Mapped[int] = mapped_column(ForeignKey("orgao_publico.id"), index=True)
    ano: Mapped[int] = mapped_column(Integer)
    nome: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    aprovado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    aprovado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
