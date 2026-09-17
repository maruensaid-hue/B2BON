from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SalaCorporativa(Base):
    """Corporate Room (master prompt §52, Fase 4A) — espaço persistente
    entre dois tenants conectados. `tenant_id_a`/`tenant_id_b` são
    sempre armazenados em ordem lexicográfica (menor primeiro) pra
    normalizar o par e evitar (A,B) e (B,A) criando duas salas
    diferentes para a mesma dupla de empresas."""

    __tablename__ = "sala_corporativa"
    __table_args__ = (UniqueConstraint("tenant_id_a", "tenant_id_b"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id_a: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    tenant_id_b: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
