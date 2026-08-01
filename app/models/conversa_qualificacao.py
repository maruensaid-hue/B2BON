from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConversaQualificacao(Base):
    """Roteiro de qualificação S.H.A.R.K. adaptativo (E5-H1)."""

    __tablename__ = "conversa_qualificacao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("conta.id"))
    decisor_id: Mapped[int] = mapped_column(ForeignKey("decisor.id"))
    canal: Mapped[str] = mapped_column(String)
    # dores | contexto | orcamento | autoridade | timing | concluida
    etapa_atual: Mapped[str] = mapped_column(String, default="dores")
    # em_andamento | transferida_humano | concluida | devolvida
    status: Mapped[str] = mapped_column(String, default="em_andamento")
    motivo_devolucao: Mapped[str | None] = mapped_column(String, nullable=True)
    transferido_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
