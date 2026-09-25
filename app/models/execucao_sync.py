from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ExecucaoSync(Base):
    """Uma rodada de sincronização de uma entidade de uma conexão (Fase 3).
    `iniciado_em` da última execução com sucesso é o `updated_since` da
    próxima (sync incremental)."""

    __tablename__ = "execucao_sync"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conexao_id: Mapped[int] = mapped_column(ForeignKey("conexao_integracao.id"), index=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    entidade: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="executando")  # executando | sucesso | falha
    incremental_desde: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    itens_lidos: Mapped[int] = mapped_column(Integer, default=0)
    paginas: Mapped[int] = mapped_column(Integer, default=0)
    tentativas: Mapped[int] = mapped_column(Integer, default=0)
    iniciado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    finalizado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    erro: Mapped[str | None] = mapped_column(String, nullable=True)
