from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConhecimentoCorporativo(Base):
    """Item do Corporate Brain do tenant (Fase 4, §15).

    Pertence ao TENANT, não ao CRM. `visibilidade="rede"` é a única forma
    de um item ser usado para responder a OUTRA empresa (Agente
    Corporativo); o default é interno. `origem`/`evidencia` mantêm a
    proveniência (§63): um aprendizado inferido nunca vira "fato"."""

    __tablename__ = "conhecimento_corporativo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    tipo: Mapped[str] = mapped_column(String, index=True)
    titulo: Mapped[str] = mapped_column(String)
    conteudo: Mapped[str] = mapped_column(Text)
    origem: Mapped[str] = mapped_column(String, default="INTERNAL")  # DataOrigin
    classificacao: Mapped[str] = mapped_column(String, default="INTERNAL")  # DataClassification
    visibilidade: Mapped[str] = mapped_column(String, default="interno")  # interno | rede
    fonte: Mapped[str | None] = mapped_column(String, nullable=True)
    evidencia: Mapped[list] = mapped_column(JSON, default=list)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_por_usuario_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
