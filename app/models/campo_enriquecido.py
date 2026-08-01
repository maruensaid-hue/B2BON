from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CampoEnriquecido(Base):
    """Histórico de proveniência por campo enriquecido de uma conta (E2-H2)."""

    __tablename__ = "campo_enriquecido"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("conta.id"))
    campo: Mapped[str] = mapped_column(String)
    valor: Mapped[str] = mapped_column(String)
    fonte: Mapped[str] = mapped_column(String)
    coletado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
