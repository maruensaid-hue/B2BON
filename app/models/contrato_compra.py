from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ContratoCompra(Base):
    """Contrato do lado comprador (§47).

    Dado CONFIDENTIAL do tenant comprador (barreira Buy/Sell, Fase 10)."""

    __tablename__ = "contrato_compra"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    orgao_id: Mapped[int] = mapped_column(ForeignKey("orgao_publico.id"), index=True)
    processo_id: Mapped[int | None] = mapped_column(ForeignKey("processo_contratacao.id"), nullable=True)
    fornecedor_id: Mapped[int] = mapped_column(ForeignKey("fornecedor_compras.id"), index=True)
    numero: Mapped[str | None] = mapped_column(String, nullable=True)
    objeto: Mapped[str] = mapped_column(Text)
    categoria: Mapped[str | None] = mapped_column(String, nullable=True)
    valor_inicial: Mapped[float | None] = mapped_column(Float, nullable=True)
    valor_atual: Mapped[float | None] = mapped_column(Float, nullable=True)
    vigencia_inicio: Mapped[date | None] = mapped_column(Date, nullable=True)
    vigencia_fim: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String)
    necessidade_continuada: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    sla: Mapped[str | None] = mapped_column(Text, nullable=True)
    garantia: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
