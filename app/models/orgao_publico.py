from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OrgaoPublico(Base):
    """Public Organization (§37): órgão/entidade compradora do tenant. Regime jurídico e parâmetros são configuráveis (não presumimos um regime único).

    Dado CONFIDENTIAL do tenant comprador (barreira Buy/Sell, Fase 10)."""

    __tablename__ = "orgao_publico"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    nome: Mapped[str] = mapped_column(String)
    cnpj: Mapped[str | None] = mapped_column(String, nullable=True)
    esfera: Mapped[str | None] = mapped_column(String, nullable=True)
    regime_juridico: Mapped[str | None] = mapped_column(String, nullable=True)
    parametros: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
