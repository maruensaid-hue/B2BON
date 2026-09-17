from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SinalOportunidade(Base):
    """Opportunity Signal (master prompt §28, §50-51, Fase 3D) — combina
    fit ICP (Fase 3B) + matches de Intent (Fase 3C) + Business Graph
    (`RelacionamentoEmpresarial`, Fase 1D) num sinal único por par
    tenant/tenant-alvo/tipo. `UniqueConstraint` garante que regerar
    sinais atualiza em vez de duplicar (geração é on-demand, não um
    cron novo)."""

    __tablename__ = "sinal_oportunidade"
    __table_args__ = (UniqueConstraint("tenant_id", "tenant_id_alvo", "tipo_sinal"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    tenant_id_alvo: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    tipo_sinal: Mapped[str] = mapped_column(String)  # fit_icp | match_intent | relacionamento_declarado
    score: Mapped[float] = mapped_column(Float)
    confianca: Mapped[str] = mapped_column(String)  # baixa | media | alta
    motivo: Mapped[str] = mapped_column(String)
    evidencias: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String, default="novo")  # novo | visto | descartado | convertido
    conta_id_gerada: Mapped[int | None] = mapped_column(ForeignKey("conta.id"), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expira_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
