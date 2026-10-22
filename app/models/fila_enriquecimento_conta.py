from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FilaEnriquecimentoConta(Base):
    """Fila de enriquecimento em lote (site + decisores) pra contas criadas
    de uma vez só (ex.: importação de planilha de evento) — processada aos
    poucos pelo cron, nunca de forma síncrona no request que criou as
    contas (uma planilha grande enriquecendo tudo na hora estouraria o
    timeout do proxy do Render, cada empresa passa por LLM + busca web +
    provedor de contatos)."""

    __tablename__ = "fila_enriquecimento_conta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("conta.id"), index=True)
    status: Mapped[str] = mapped_column(String, default="pendente")  # pendente | concluido | falhou
    # IA indisponível não é falha definitiva: a conta volta para a fila com espera crescente, até o limite de tentativas.
    tentativas: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    proxima_tentativa_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    erro: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    processado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
