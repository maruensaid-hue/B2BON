from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Decisor(Base):
    __tablename__ = "decisor"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("conta.id"))
    nome: Mapped[str] = mapped_column(String)
    cargo: Mapped[str | None] = mapped_column(String, nullable=True)
    canal_provavel: Mapped[str | None] = mapped_column(String, nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    telefone: Mapped[str | None] = mapped_column(String, nullable=True)
    neo4j_node_id: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
