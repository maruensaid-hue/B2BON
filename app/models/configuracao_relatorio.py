from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConfiguracaoRelatorio(Base):
    """Cadência de relatório periódico (Fase 3 da hierarquia, raio-X) —
    volumetria/franquia/inadimplência/receita/churn, um por tenant (quem
    configura pode ser super_admin, distribuidor ou revendedor; o escopo
    agregado é resolvido por papel na hora do envio, não aqui)."""

    __tablename__ = "configuracao_relatorio"
    __table_args__ = (UniqueConstraint("tenant_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    # "diaria" | "semanal" | "mensal" | "desativada"
    cadencia: Mapped[str] = mapped_column(String, default="desativada")
    ultimo_envio_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
