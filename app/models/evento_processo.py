from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EventoProcesso(Base):
    """Aprovações, esclarecimentos, tarefas e marcos do processo (timeline, §41).

    Dado CONFIDENTIAL do tenant comprador (barreira Buy/Sell, Fase 10)."""

    __tablename__ = "evento_processo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    processo_id: Mapped[int] = mapped_column(ForeignKey("processo_contratacao.id"), index=True)
    tipo: Mapped[str] = mapped_column(String)
    descricao: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String)
    prazo: Mapped[date | None] = mapped_column(Date, nullable=True)
    responsavel_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    criado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    concluido_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
