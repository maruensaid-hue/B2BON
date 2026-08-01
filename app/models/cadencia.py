from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Cadencia(Base):
    __tablename__ = "cadencia"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    # Nullable: a cadência é um blueprint multicanal aplicado a um lote de
    # contas (E3-H1), não presa a uma única conta — o vínculo real com cada
    # conta se dá via Mensagem -> Decisor -> Conta.
    conta_id: Mapped[int | None] = mapped_column(ForeignKey("conta.id"), nullable=True)
    nome: Mapped[str] = mapped_column(String)
    canais: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(
        String
    )  # rascunho | aguardando_aprovacao | ativa
    data_inicio: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
