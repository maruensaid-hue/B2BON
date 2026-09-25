from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CarteiraCreditos(Base):
    """Carteira de AI Credits compartilhada pelo tenant (Fase 5, §56)."""

    __tablename__ = "carteira_creditos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), unique=True)
    saldo: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MovimentoCredito(Base):
    """Extrato imutável da carteira. `saldo_apos` permite auditoria linha a linha."""

    __tablename__ = "movimento_credito"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    tipo: Mapped[str] = mapped_column(String)  # ALOCACAO | CONSUMO | EXCEDENTE | AJUSTE | ESTORNO
    quantidade: Mapped[float] = mapped_column(Numeric(18, 4))
    saldo_apos: Mapped[float] = mapped_column(Numeric(18, 4))
    registro_uso_ia_id: Mapped[int | None] = mapped_column(ForeignKey("registro_uso_ia.id"), nullable=True, index=True)
    descricao: Mapped[str | None] = mapped_column(String, nullable=True)
    ator_id: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
