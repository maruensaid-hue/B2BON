from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConteudoPaginaSite(Base):
    """Texto coletado de cada página do site institucional de uma conta (a última coleta de cada URL).

    A coleta é determinística e independe de IA: guardar o conteúdo permite refazer a análise sem acessar o site de
    novo e deixa a origem de cada sinal verificável. Uma linha por (conta, URL) — coletar de novo atualiza em vez de
    acumular versões, o que limita o armazenamento (≈ 2.500 caracteres por página, no máximo 8 páginas por conta)."""

    __tablename__ = "conteudo_pagina_site"
    __table_args__ = (UniqueConstraint("conta_id", "url", name="uq_conteudo_pagina_site_conta_url"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("conta.id"), index=True)
    url: Mapped[str] = mapped_column(String)
    conteudo: Mapped[str] = mapped_column(Text)
    coletado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
