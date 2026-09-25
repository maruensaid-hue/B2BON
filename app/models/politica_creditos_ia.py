from datetime import datetime

from sqlalchemy import Boolean, DateTime, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PoliticaCreditosIa(Base):
    """Conversão custo → B2B ON AI Credits (Fase 5, §55).

    Decisão comercial do Product Owner. Enquanto `status =
    PENDING_DEFINITION` (e `creditos_por_usd` nulo), o custo é medido mas
    nenhum crédito é debitado — o sistema não inventa a taxa. Nunca é
    exposto publicamente como "1 crédito = X tokens"."""

    __tablename__ = "politica_creditos_ia"

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String, default="PENDING_DEFINITION")  # PENDING_DEFINITION | ATIVA | INATIVA
    creditos_por_usd: Mapped[float | None] = mapped_column(Numeric(14, 4), nullable=True)
    permite_excedente: Mapped[bool] = mapped_column(Boolean, default=False)
    exige_saldo: Mapped[bool] = mapped_column(Boolean, default=False)
    observacao: Mapped[str | None] = mapped_column(String, nullable=True)
    vigente_desde: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
