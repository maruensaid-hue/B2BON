from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ContratoVendaPublica(Base):
    """Contrato ganho pelo tenant (Contract Intelligence do lado vendedor):
    vigência e renovação alimentam o Deadline Engine."""

    __tablename__ = "contrato_venda_publica"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    licitacao_id: Mapped[int | None] = mapped_column(ForeignKey("licitacao.id"), nullable=True)
    conta_id: Mapped[int | None] = mapped_column(ForeignKey("conta.id"), nullable=True)
    orgao_nome: Mapped[str | None] = mapped_column(String, nullable=True)
    numero: Mapped[str | None] = mapped_column(String, nullable=True)
    objeto: Mapped[str] = mapped_column(String)
    valor: Mapped[float | None] = mapped_column(Float, nullable=True)
    vigencia_inicio: Mapped[date | None] = mapped_column(Date, nullable=True)
    vigencia_fim: Mapped[date | None] = mapped_column(Date, nullable=True)
    renovavel: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    status: Mapped[str] = mapped_column(String)  # VIGENTE | ENCERRADO | RESCINDIDO
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
