from datetime import date, datetime

from sqlalchemy import Date, DateTime, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PrecoModeloIa(Base):
    """Custo do PROVEDOR por modelo, versionado por vigência (Fase 5, §54).

    É custo da B2B ON, não preço ao cliente. Valores em USD por milhão de
    tokens. Uma troca de preço é uma NOVA linha com `vigente_desde`
    posterior — o histórico de custo nunca é recalculado em silêncio."""

    __tablename__ = "preco_modelo_ia"
    __table_args__ = (UniqueConstraint("provider", "modelo", "vigente_desde"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String)
    modelo: Mapped[str] = mapped_column(String, index=True)
    vigente_desde: Mapped[date] = mapped_column(Date)
    entrada_usd_mtok: Mapped[float] = mapped_column(Numeric(12, 6))
    saida_usd_mtok: Mapped[float] = mapped_column(Numeric(12, 6))
    cache_escrita_usd_mtok: Mapped[float] = mapped_column(Numeric(12, 6))
    cache_leitura_usd_mtok: Mapped[float] = mapped_column(Numeric(12, 6))
    fonte: Mapped[str] = mapped_column(String)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
