from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class QuotaComercial(Base):
    """Quota de um representante por competência (MAP Performance, D-080) — versionada: mudar a quota cria uma versão
    nova (a anterior fica inativa, nunca é apagada) e a mudança é auditada.

    `representante_id` nulo = quota padrão de cada representante ativo naquela competência; uma linha com o
    representante vale só para ele e prevalece sobre a padrão. A quota da equipe é a soma das quotas efetivas.
    `pipeline_alvo` é o target gerencial de pipeline qualificado (ex.: R$ 30.000 em Out/26); sem ele, o alvo é
    `multiplo_cobertura` × quota."""

    __tablename__ = "quota_comercial"
    __table_args__ = (UniqueConstraint("representante_id", "metrica", "competencia", "versao"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    representante_id: Mapped[int | None] = mapped_column(ForeignKey("representante.id"), nullable=True, index=True)
    metrica: Mapped[str] = mapped_column(String)  # NEW_MRR
    competencia: Mapped[str] = mapped_column(String, index=True)  # YYYY-MM
    valor: Mapped[float] = mapped_column(Float)
    multiplo_cobertura: Mapped[float | None] = mapped_column(Float, nullable=True)
    pipeline_alvo: Mapped[float | None] = mapped_column(Float, nullable=True)
    versao: Mapped[int] = mapped_column(Integer, default=1)
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)
    motivo: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
