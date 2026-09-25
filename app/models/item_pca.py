from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ItemPca(Base):
    """Item do PCA (§39).

    Dado CONFIDENTIAL do tenant comprador (barreira Buy/Sell, Fase 10)."""

    __tablename__ = "item_pca"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    plano_id: Mapped[int] = mapped_column(ForeignKey("plano_contratacao.id"), index=True)
    descricao: Mapped[str] = mapped_column(String)
    categoria: Mapped[str | None] = mapped_column(String, nullable=True)
    valor_estimado: Mapped[float | None] = mapped_column(Float, nullable=True)
    data_prevista: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
