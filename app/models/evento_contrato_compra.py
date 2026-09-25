from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EventoContratoCompra(Base):
    """Aditivos, entregas, fiscalizações, pagamentos e ocorrências (§47). Ocorrência sem contrato fica no fornecedor.

    Dado CONFIDENTIAL do tenant comprador (barreira Buy/Sell, Fase 10)."""

    __tablename__ = "evento_contrato_compra"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    fornecedor_id: Mapped[int] = mapped_column(ForeignKey("fornecedor_compras.id"), index=True)
    contrato_id: Mapped[int | None] = mapped_column(ForeignKey("contrato_compra.id"), nullable=True)
    tipo: Mapped[str] = mapped_column(String)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    valor: Mapped[float | None] = mapped_column(Float, nullable=True)
    nota: Mapped[float | None] = mapped_column(Float, nullable=True)
    data: Mapped[date | None] = mapped_column(Date, nullable=True)
    criado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
