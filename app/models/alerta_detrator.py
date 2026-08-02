from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AlertaDetrator(Base):
    """Alerta imediato ao Gestor Comercial quando um detrator é identificado (E11-H1)."""

    __tablename__ = "alerta_detrator"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    pesquisa_nps_id: Mapped[int] = mapped_column(ForeignKey("pesquisa_nps.id"))
    conta_id: Mapped[int] = mapped_column(ForeignKey("conta.id"))
    decisor_id: Mapped[int] = mapped_column(ForeignKey("decisor.id"))
    nota: Mapped[int] = mapped_column(Integer)
    sugestao_acao: Mapped[str] = mapped_column(String)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
