from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditLog(Base):
    """Registro imutável de eventos — trilha de auditoria (E4-H3 / E9)."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    evento_tipo: Mapped[str] = mapped_column(String)
    entidade_tipo: Mapped[str] = mapped_column(String)
    entidade_id: Mapped[int] = mapped_column(Integer)
    ator_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # Denormalizados para permitir filtro direto por conta/canal sem join (E4-H3).
    conta_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    canal: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    detalhes: Mapped[dict] = mapped_column(JSON, default=dict)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
