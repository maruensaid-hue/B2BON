from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConfiguracaoComunicacao(Base):
    __tablename__ = "configuracao_comunicacao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    tom: Mapped[str] = mapped_column(String)  # formal | consultivo | direto
    restricoes: Mapped[list] = mapped_column(JSON, default=list)
    # Resposta do lead gera um RASCUNHO de resposta (fila de aprovação) que conduz para a reunião; desligar = só o vendedor responde.
    rascunho_resposta: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    # Página de agenda do vendedor (Calendly, Google Agenda...): o rascunho a oferece em vez de pedir dia e horário.
    link_agendamento: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
