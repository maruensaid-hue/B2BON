from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TurnoConversa(Base):
    """Conversa completa registrada na linha do tempo da conta (E5-H1)."""

    __tablename__ = "turno_conversa"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    conversa_id: Mapped[int] = mapped_column(ForeignKey("conversa_qualificacao.id"))
    direcao: Mapped[str] = mapped_column(String)  # entrada | saida
    conteudo: Mapped[str] = mapped_column(String)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
