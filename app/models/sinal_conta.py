from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SinalConta(Base):
    """Um fato observado sobre uma conta: uma LINHA por observação, nunca uma coluna nova em `conta`.

    Sinal novo não exige migração (basta um código no catálogo `app.contexts.predator.sinais`), a confiança e a evidência viajam com
    o fato, e observar de novo cria outra linha: a anterior deixa de ser `vigente`, mas continua consultável (a mudança é histórico).
    A ausência de dado nunca vira sinal negativo: só é gravado o que a fonte de fato mostrou (ou, para página do site, o que a coleta
    procurou e não achou)."""

    __tablename__ = "sinal_conta"
    __table_args__ = (Index("ix_sinal_conta_conta_codigo_vigente", "conta_id", "codigo", "vigente"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("conta.id"), index=True)
    codigo: Mapped[str] = mapped_column(String, index=True)
    valor_num: Mapped[float | None] = mapped_column(Float, nullable=True)  # booleano = 1/0
    valor_texto: Mapped[str | None] = mapped_column(String, nullable=True)
    confianca: Mapped[float] = mapped_column(Float)  # 0 a 1
    fonte: Mapped[str] = mapped_column(String)  # pesquisa_no_site | verificacao_dominio | indicadores_site | cadastro_publico_cnpj
    url_evidencia: Mapped[str | None] = mapped_column(String, nullable=True)
    trecho: Mapped[str | None] = mapped_column(Text, nullable=True)
    coleta_id: Mapped[int | None] = mapped_column(ForeignKey("coleta_site_conta.id"), index=True, nullable=True)
    vigente: Mapped[bool] = mapped_column(Boolean, default=True)
    observado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
