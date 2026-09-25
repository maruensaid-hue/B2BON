from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProcessoContratacao(Base):
    """Procurement Process (§41): o workspace de cada contratação.

    Dado CONFIDENTIAL do tenant comprador (barreira Buy/Sell, Fase 10)."""

    __tablename__ = "processo_contratacao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    orgao_id: Mapped[int] = mapped_column(ForeignKey("orgao_publico.id"), index=True)
    unidade_id: Mapped[int | None] = mapped_column(ForeignKey("unidade_compras.id"), nullable=True)
    item_pca_id: Mapped[int | None] = mapped_column(ForeignKey("item_pca.id"), nullable=True)
    numero: Mapped[str | None] = mapped_column(String, nullable=True)
    objeto: Mapped[str] = mapped_column(Text)
    modalidade: Mapped[str | None] = mapped_column(String, nullable=True)
    categoria: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String)
    valor_estimado: Mapped[float | None] = mapped_column(Float, nullable=True)
    valor_sigiloso: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    prazo_previsto: Mapped[date | None] = mapped_column(Date, nullable=True)
    publicado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    responsavel_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    demanda_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
