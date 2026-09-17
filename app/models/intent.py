from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Intent(Base):
    """Business Intent (master prompt §46-47, Fase 3A) — necessidade
    comercial declarada por um tenant, visível pra rede conforme
    `visibilidade`. Camada livre da Rede Social (mesmo grupo sem
    licença de Posts/Feed) — a inteligência que consome isso
    (fit/matching/sinais) é que exige licença (Fase 3B-3D)."""

    __tablename__ = "intent"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    categoria: Mapped[str] = mapped_column(String)
    titulo: Mapped[str] = mapped_column(String)
    descricao: Mapped[str] = mapped_column(String)
    requisitos: Mapped[list] = mapped_column(JSON, default=list)
    faixa_orcamento: Mapped[str | None] = mapped_column(String, nullable=True)
    localizacao: Mapped[str | None] = mapped_column(String, nullable=True)
    prazo: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    perfil_fornecedor_desejado: Mapped[str | None] = mapped_column(String, nullable=True)
    visibilidade: Mapped[str] = mapped_column(String, default="publica")  # publica | conexoes
    status: Mapped[str] = mapped_column(String, default="aberta")  # aberta | atendida | expirada | cancelada
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expira_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
