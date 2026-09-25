from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RegistroUsoIa(Base):
    """Ledger de uso de IA (Fase 7C original; ampliado na Fase 4 do Master
    Prompt v4, §54/§73). Uma linha por chamada ao LLM feita pelo AI
    Gateway — sucesso OU falha. Custo e créditos entram na Fase 5 (tabela
    de preço versionada); aqui só fatos medidos."""

    __tablename__ = "registro_uso_ia"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    agente: Mapped[str] = mapped_column(String)
    tokens_entrada: Mapped[int] = mapped_column(Integer)
    tokens_saida: Mapped[int] = mapped_column(Integer)
    latencia_ms: Mapped[int] = mapped_column(Integer)
    model: Mapped[str | None] = mapped_column(String, nullable=True)
    entidade_tipo: Mapped[str | None] = mapped_column(String, nullable=True)
    entidade_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # --- Fase 4 -------------------------------------------------------------
    usuario_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    modulo: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    feature: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    workflow: Mapped[str | None] = mapped_column(String, nullable=True)
    provider: Mapped[str | None] = mapped_column(String, nullable=True)
    classe_modelo: Mapped[str | None] = mapped_column(String, nullable=True)
    gatilho: Mapped[str | None] = mapped_column(String, nullable=True)  # usuario | automatico | api
    tokens_cache_leitura: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    tokens_cache_escrita: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String, default="sucesso", server_default="sucesso")  # sucesso | falha | bloqueado
    erro: Mapped[str | None] = mapped_column(String, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # --- Fase 5 (FinOps) ------------------------------------------------------
    custo_usd: Mapped[float | None] = mapped_column(Numeric(18, 8), nullable=True)  # None = modelo sem preço cadastrado
    preco_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    creditos_consumidos: Mapped[float | None] = mapped_column(Numeric(18, 4), nullable=True)  # None = política pendente
