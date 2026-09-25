from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PerfilInteligencia(Base):
    """Company / User Intelligence (Fase 4, §16, §59). Resultado da
    consolidação de memória: histórico volumoso → conhecimento estruturado,
    com as fontes e amostras de cada campo em `fontes`."""

    __tablename__ = "perfil_inteligencia"
    __table_args__ = (UniqueConstraint("tenant_id", "escopo", "usuario_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    escopo: Mapped[str] = mapped_column(String)  # empresa | usuario
    usuario_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dados: Mapped[dict] = mapped_column(JSON, default=dict)
    fontes: Mapped[dict] = mapped_column(JSON, default=dict)
    versao: Mapped[int] = mapped_column(Integer, default=1)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
