from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConfiguracaoPainel(Base):
    """Meta mensal da métrica-norte, configurável por assinante (E8-H1)."""

    __tablename__ = "configuracao_painel"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    meta_mensal_reunioes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
