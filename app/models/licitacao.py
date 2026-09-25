from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Licitacao(Base):
    """Bid Opportunity (master prompt §31-§32, Fase 9): licitação, RFP/RFI/RFQ
    ou processo privado que o tenant (vendedor) acompanha. Dado CONFIDENTIAL
    do tenant: nunca atravessa para outro tenant nem para o lado comprador
    (barreira Buy/Sell, Fase 10)."""

    __tablename__ = "licitacao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    titulo: Mapped[str] = mapped_column(String)
    objeto: Mapped[str | None] = mapped_column(Text, nullable=True)
    orgao_nome: Mapped[str | None] = mapped_column(String, nullable=True)
    orgao_cnpj: Mapped[str | None] = mapped_column(String, nullable=True)
    conta_id: Mapped[int | None] = mapped_column(ForeignKey("conta.id"), nullable=True)
    oferta_id: Mapped[int | None] = mapped_column(ForeignKey("oferta.id"), nullable=True)
    modalidade: Mapped[str] = mapped_column(String)
    fonte: Mapped[str] = mapped_column(String)  # MANUAL | PNCP
    fonte_id_externo: Mapped[str | None] = mapped_column(String, nullable=True)
    fonte_url: Mapped[str | None] = mapped_column(String, nullable=True)
    data_publicacao: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    prazo_proposta: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    prazo_esclarecimento: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    valor_estimado: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String)
    responsavel_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    concorrentes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    parceiros: Mapped[list | None] = mapped_column(JSON, nullable=True)
    vencedor: Mapped[str | None] = mapped_column(String, nullable=True)
    valor_proposta: Mapped[float | None] = mapped_column(Float, nullable=True)
    motivo_resultado: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


Index(
    "ix_licitacao_fonte_externa_unica",
    Licitacao.tenant_id,
    Licitacao.fonte,
    Licitacao.fonte_id_externo,
    unique=True,
    postgresql_where=(Licitacao.fonte_id_externo.isnot(None)),
    sqlite_where=(Licitacao.fonte_id_externo.isnot(None)),
)
