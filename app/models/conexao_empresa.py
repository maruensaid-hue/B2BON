from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConexaoEmpresa(Base):
    """Conexão entre dois assinantes — "conexões qualificadas" da fase
    Encantar do Flywheel (Onda C)."""

    __tablename__ = "conexao_empresa"
    __table_args__ = (UniqueConstraint("tenant_id_origem", "tenant_id_destino"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id_origem: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    tenant_id_destino: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    status: Mapped[str] = mapped_column(String, default="pendente")  # pendente | aceita | recusada
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    respondida_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
