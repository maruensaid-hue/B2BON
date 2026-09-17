from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PostRedeSocial(Base):
    """Business Feed (master prompt §44-45, Fase 2B) — escopo reduzido:
    sem upload de arquivo (imagem/link são URLs coladas, mesmo padrão
    já usado no logo/capa do Corporate Profile), sem vídeo/documentos/
    produtos/eventos/intents como anexo (dependem de storage real ou
    de entidades que ainda não existem, como Intent — Fase 3)."""

    __tablename__ = "post_rede_social"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    usuario_autor_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    texto: Mapped[str] = mapped_column(String)
    imagem_url: Mapped[str | None] = mapped_column(String, nullable=True)
    link_url: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
