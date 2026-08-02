from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Indicacao(Base):
    """Pedido de indicação a um promotor e seu rastreio até virar negócio (E11-H2/H3)."""

    __tablename__ = "indicacao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    promotor_decisor_id: Mapped[int] = mapped_column(ForeignKey("decisor.id"))
    promotor_conta_id: Mapped[int] = mapped_column(ForeignKey("conta.id"))
    codigo_indicacao: Mapped[str] = mapped_column(String, unique=True, index=True)
    canal: Mapped[str] = mapped_column(String)
    indicado_nome: Mapped[str | None] = mapped_column(String, nullable=True)
    indicado_identificador: Mapped[str | None] = mapped_column(String, nullable=True)
    intra_rede: Mapped[bool] = mapped_column(Boolean, default=False)
    conta_gerada_id: Mapped[int | None] = mapped_column(ForeignKey("conta.id"), nullable=True)
    status: Mapped[str] = mapped_column(String, default="aguardando")  # aguardando | convertida
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    convertida_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
