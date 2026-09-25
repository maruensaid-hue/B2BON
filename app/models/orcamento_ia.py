from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OrcamentoIa(Base):
    """Budget / quota mensal de IA (Fase 5). `escopo`: tenant | modulo |
    feature (com `alvo`). Limite em USD de custo ou em número de chamadas.
    `acao`: ALERTAR (só sinaliza) | BLOQUEAR (o gateway recusa a chamada)."""

    __tablename__ = "orcamento_ia"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    escopo: Mapped[str] = mapped_column(String, default="tenant")
    alvo: Mapped[str | None] = mapped_column(String, nullable=True)
    limite_custo_usd: Mapped[float | None] = mapped_column(Numeric(14, 4), nullable=True)
    limite_chamadas: Mapped[int | None] = mapped_column(Integer, nullable=True)
    acao: Mapped[str] = mapped_column(String, default="ALERTAR")
    percentual_alerta: Mapped[int] = mapped_column(Integer, default=80)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
