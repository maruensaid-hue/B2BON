from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CanalSala(Base):
    """Channel dentro de uma Corporate Room (master prompt §53, Fase
    4A). `GENERAL` nasce automático ao abrir a sala; os demais tipos
    nomeados do documento (COMMERCIAL/TECHNICAL/LEGAL/PROCUREMENT/
    FINANCIAL/SUPPORT) e `CUSTOM` são criados manualmente."""

    __tablename__ = "canal_sala"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sala_id: Mapped[int] = mapped_column(ForeignKey("sala_corporativa.id"), index=True)
    tipo: Mapped[str] = mapped_column(String)
    nome: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    # INTERNAL/SHARED (master prompt §54, Fase 5A) — "interno" só é
    # visível pra quem criou o canal (`criado_por`); "compartilhado" é
    # visível pros dois lados da sala, mesmo comportamento de antes.
    escopo: Mapped[str] = mapped_column(String, default="compartilhado")
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
