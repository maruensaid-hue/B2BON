from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EnriquecimentoSemanalConsumo(Base):
    """Log de consumo do limite semanal de pesquisas de enriquecimento
    (raio-X 2026-08-27, `enriquecimento_limite_service`) — uma linha por
    pesquisa bem-sucedida, sem unique constraint (diferente de
    `ContaFranquiaConsumo`, que dedupe por conta; aqui cada chamada conta
    de novo, mesmo pra mesma conta). `tipo` distingue "site" (`conta_
    service.enriquecer`) de "contatos" (`conta_service.mapear_
    decisores`) — contadores independentes."""

    __tablename__ = "enriquecimento_semanal_consumo"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    tipo: Mapped[str] = mapped_column(String)  # "site" | "contatos"
    semana: Mapped[str] = mapped_column(String)  # ISO "YYYY-Www"
    consumido_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
