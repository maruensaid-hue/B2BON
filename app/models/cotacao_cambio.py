"""Cotação de câmbio (OI-018, D-075): fonte única da conversão de custos em moeda estrangeira (ex.: IA em USD).

Nenhuma cotação fica no código ou em variável de ambiente. Cada linha é uma cotação informada, com fonte e o instante a
partir do qual vale; a cotação aplicável a um custo é a mais recente com `vigente_em` até o instante do custo.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, Index, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CotacaoCambio(Base):
    __tablename__ = "cotacao_cambio"
    __table_args__ = (Index("ix_cotacao_cambio_par_vigencia", "moeda_base", "moeda_cotacao", "vigente_em"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    moeda_base: Mapped[str] = mapped_column(String(3))  # base_currency (ex.: USD)
    moeda_cotacao: Mapped[str] = mapped_column(String(3))  # quote_currency (ex.: BRL)
    taxa: Mapped[Decimal] = mapped_column(Numeric(14, 6))  # 1 moeda_base = taxa moeda_cotacao
    fonte: Mapped[str] = mapped_column(String)  # ex.: PTAX venda BCB
    vigente_em: Mapped[datetime] = mapped_column(DateTime)  # effective_at
    criado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
