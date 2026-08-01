from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TarefaLinkedin(Base):
    """Tarefa assistida de LinkedIn — nunca enviada automaticamente (E3-H4)."""

    __tablename__ = "tarefa_linkedin"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    mensagem_id: Mapped[int] = mapped_column(ForeignKey("mensagem.id"))
    decisor_id: Mapped[int] = mapped_column(ForeignKey("decisor.id"))
    texto: Mapped[str] = mapped_column(String)
    link_perfil: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pendente")  # pendente | executada | ignorada
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
