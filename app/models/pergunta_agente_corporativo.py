from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PerguntaAgenteCorporativo(Base):
    """Pergunta de um tenant ao Corporate AI Agent de outro (master
    prompt §57-58, Fase 6A). `resposta_rascunho` é sempre gerada
    primeiro (ou o texto canned de "sem evidência") — só vira visível
    pro perguntante depois que um humano do tenant_id_alvo aprova/
    edita (`resposta_final`), nunca antes (Human-in-the-loop, §4)."""

    __tablename__ = "pergunta_agente_corporativo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id_alvo: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    tenant_id_perguntante: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    pergunta: Mapped[str] = mapped_column(String)
    resposta_rascunho: Mapped[str | None] = mapped_column(String, nullable=True)
    resposta_final: Mapped[str | None] = mapped_column(String, nullable=True)
    evidencias: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String, default="pendente_aprovacao")
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    respondido_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    respondido_por: Mapped[str | None] = mapped_column(String, nullable=True)
