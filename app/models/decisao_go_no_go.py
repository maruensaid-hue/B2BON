from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DecisaoGoNoGo(Base):
    """Go/No-Go (§35): a decisão é humana; a recomendação e os fatores que a
    precederam ficam gravados junto, para auditoria."""

    __tablename__ = "decisao_go_no_go"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    licitacao_id: Mapped[int] = mapped_column(ForeignKey("licitacao.id"), index=True)
    recomendacao: Mapped[str] = mapped_column(String)
    fatores: Mapped[list] = mapped_column(JSON)
    decisao: Mapped[str] = mapped_column(String)  # GO | NO_GO
    justificativa: Mapped[str | None] = mapped_column(String, nullable=True)
    decidido_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
