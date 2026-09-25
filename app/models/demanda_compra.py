from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DemandaCompra(Base):
    """Demand (§40): necessidade de uma unidade, sempre com revisão humana.

    Dado CONFIDENTIAL do tenant comprador (barreira Buy/Sell, Fase 10)."""

    __tablename__ = "demanda_compra"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    unidade_id: Mapped[int] = mapped_column(ForeignKey("unidade_compras.id"))
    solicitante_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    necessidade: Mapped[str] = mapped_column(Text)
    justificativa: Mapped[str | None] = mapped_column(Text, nullable=True)
    categoria: Mapped[str | None] = mapped_column(String, nullable=True)
    valor_estimado: Mapped[float | None] = mapped_column(Float, nullable=True)
    prioridade: Mapped[str | None] = mapped_column(String, nullable=True)
    data_necessaria: Mapped[date | None] = mapped_column(Date, nullable=True)
    referencia_orcamentaria: Mapped[str | None] = mapped_column(String, nullable=True)
    item_pca_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String)
    aprovado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    aprovado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
