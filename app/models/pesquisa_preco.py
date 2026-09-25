from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PesquisaPreco(Base):
    """Price Research foundation: preço coletado com fonte. A plataforma não inventa preço.

    Dado CONFIDENTIAL do tenant comprador (barreira Buy/Sell, Fase 10)."""

    __tablename__ = "pesquisa_preco"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    processo_id: Mapped[int] = mapped_column(ForeignKey("processo_contratacao.id"), index=True)
    item_descricao: Mapped[str] = mapped_column(String)
    unidade: Mapped[str | None] = mapped_column(String, nullable=True)
    preco_unitario: Mapped[float] = mapped_column(Float)
    fonte_tipo: Mapped[str] = mapped_column(String)
    fonte_descricao: Mapped[str] = mapped_column(String)
    data_coleta: Mapped[date | None] = mapped_column(Date, nullable=True)
    documento_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
