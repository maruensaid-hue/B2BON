from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SeguidorEmpresa(Base):
    """FOLLOWING (master prompt §43, Fase 2A) — unidirecional, sem
    aceite, distinto de `ConexaoEmpresa` (bilateral, exige aceite):
    dá pra seguir uma empresa sem estar conectado, ou já estar
    conectado e seguir também — os dois conceitos são independentes."""

    __tablename__ = "seguidor_empresa"
    __table_args__ = (UniqueConstraint("tenant_id_seguidor", "tenant_id_seguido"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id_seguidor: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    tenant_id_seguido: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
