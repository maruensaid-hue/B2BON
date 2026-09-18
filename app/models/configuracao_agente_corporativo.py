from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConfiguracaoAgenteCorporativo(Base):
    """Corporate AI Agent (master prompt §57-58, Fase 6A) — modo do
    agente que outras empresas da rede podem consultar. Sem modo
    EXTERNAL (resposta automática exigiria um policy engine que não
    existe): disabled | interno | assistido."""

    __tablename__ = "configuracao_agente_corporativo"
    __table_args__ = (UniqueConstraint("tenant_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    modo: Mapped[str] = mapped_column(String, default="disabled")
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
