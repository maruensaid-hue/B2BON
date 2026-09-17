from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MensagemSala(Base):
    """Mensagem de um canal de Corporate Room (master prompt §53, Fase
    4A) — lista plana cronológica, sem threads (mesma decisão já
    tomada pros comentários de post, Fase 2C). `documento_url` é um
    link colado, sem upload/armazenamento de arquivo novo (mesmo
    padrão de Posts/Perfil)."""

    __tablename__ = "mensagem_sala"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canal_id: Mapped[int] = mapped_column(ForeignKey("canal_sala.id"), index=True)
    tenant_id_remetente: Mapped[str] = mapped_column(ForeignKey("tenant.id"))
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    texto: Mapped[str] = mapped_column(String)
    documento_url: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
