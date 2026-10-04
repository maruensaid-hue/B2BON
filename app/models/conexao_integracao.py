from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.crypto import TextoCriptografado
from app.db.base import Base


class ConexaoIntegracao(Base):
    """Conexão de um tenant a um conector do Integration Hub (Fase 3).
    `credenciais` (tokens OAuth, API keys de terceiros) ficam
    criptografadas em repouso e nunca voltam em resposta de API.
    Escrita no CRM (D-087) é opt-in em `escrita`; ver `integrations/escrita.py`."""

    __tablename__ = "conexao_integracao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    sistema: Mapped[str] = mapped_column(String)
    nome: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="ativa")  # ativa | pausada | erro
    credenciais: Mapped[str | None] = mapped_column(TextoCriptografado, nullable=True)
    configuracao: Mapped[dict] = mapped_column(JSON, default=dict)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    ultimo_sync_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ultimo_erro: Mapped[str | None] = mapped_column(String, nullable=True)
    # D-087: escrita no CRM do cliente — opt-in por capacidade (predator, map),
    # deduplicação, funil/estágio, donos e campos próprios da B2B ON.
    escrita: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)
    # D-087: webhook de entrada — só o hash do token da URL fica no banco.
    webhook_token_hash: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # D-087: webhook recebido → o cron faz o sync incremental (nunca no request).
    sync_solicitado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
