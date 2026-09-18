from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SalaCompra(Base):
    """Digital Buying Room (master prompt §55, Fase 5A) — camada fina
    sobre a Sala Corporativa (Fase 4A): só vincula uma sala já existente
    a um `Negocio` real do tenant vendedor. Reaproveita o `EstagioFunil`
    de 5 estágios que já existe como "estágio da compra" — não cria um
    funil paralelo com o enum de 10 estágios do master prompt (§1: não
    crie um CRM paralelo)."""

    __tablename__ = "sala_compra"
    __table_args__ = (UniqueConstraint("sala_corporativa_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sala_corporativa_id: Mapped[int] = mapped_column(ForeignKey("sala_corporativa.id"), index=True)
    tenant_id_vendedor: Mapped[str] = mapped_column(ForeignKey("tenant.id"))
    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocio.id"))
    visivel_para_comprador: Mapped[bool] = mapped_column(Boolean, default=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
