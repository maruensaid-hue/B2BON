from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Aprovacao(Base):
    __tablename__ = "aprovacao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    mensagem_id: Mapped[int] = mapped_column(ForeignKey("mensagem.id"))
    status: Mapped[str] = mapped_column(String)  # pendente | aprovado | editado | rejeitado
    aprovador_id: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    decidido_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
