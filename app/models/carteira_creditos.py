from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy import false as sa_false
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CarteiraCreditos(Base):
    """Carteira de AI Credits compartilhada pelo tenant (Fase 5, §56).

    Fase 15: a fonte do saldo são os lotes (`lote_credito`) e o extrato.
    `saldo` fica como espelho (soma dos lotes ativos) e a linha serve de
    trava por tenant (`SELECT … FOR UPDATE`) para reservas concorrentes."""

    __tablename__ = "carteira_creditos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), unique=True)
    saldo: Mapped[float] = mapped_column(Numeric(18, 4), default=0)
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class MovimentoCredito(Base):
    """Extrato imutável da carteira. `saldo_apos` permite auditoria linha a linha."""

    __tablename__ = "movimento_credito"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    # Fase 5: ALOCACAO | CONSUMO | EXCEDENTE | AJUSTE | ESTORNO (histórico preservado)
    # Fase 15: CREDIT_GRANTED | CREDIT_CONSUMED | CREDIT_EXPIRED | CREDIT_PURCHASED | CREDIT_REFUNDED |
    #          CREDIT_ADJUSTED | CREDIT_PROMOTIONAL | CREDIT_OVERAGE | CREDIT_RESERVED | CREDIT_RELEASED
    tipo: Mapped[str] = mapped_column(String)
    quantidade: Mapped[float] = mapped_column(Numeric(18, 4))
    saldo_apos: Mapped[float] = mapped_column(Numeric(18, 4))
    registro_uso_ia_id: Mapped[int | None] = mapped_column(ForeignKey("registro_uso_ia.id"), nullable=True, index=True)
    descricao: Mapped[str | None] = mapped_column(String, nullable=True)
    ator_id: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # --- Fase 15 --------------------------------------------------------------
    lote_id: Mapped[int | None] = mapped_column(ForeignKey("lote_credito.id"), nullable=True, index=True)
    execucao_id: Mapped[str | None] = mapped_column(ForeignKey("execucao_ia.id"), nullable=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String, nullable=True)
    receita_brl: Mapped[float | None] = mapped_column(Numeric(14, 4), nullable=True)
    catalogo_versao: Mapped[str | None] = mapped_column(String, nullable=True)
    faturavel: Mapped[bool] = mapped_column(Boolean, default=False, server_default=sa_false())
