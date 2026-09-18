from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RegistroUsoIa(Base):
    """Observabilidade de custo/latência de IA (master prompt §85, Fase
    7C) — só o que já é fato real (tokens/latência), sem calcular
    `provider_cost` em R$/US$ (tabela de preço por modelo ficaria
    desatualizada silenciosamente — mesma cautela de "não inventar
    fato" aplicada a número)."""

    __tablename__ = "registro_uso_ia"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    agente: Mapped[str] = mapped_column(String)  # corporate_ai_agent | meeting_agent | sales_strategy_agent
    tokens_entrada: Mapped[int] = mapped_column(Integer)
    tokens_saida: Mapped[int] = mapped_column(Integer)
    latencia_ms: Mapped[int] = mapped_column(Integer)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
