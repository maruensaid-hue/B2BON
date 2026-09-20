from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PostRedeSocial(Base):
    """Business Feed (master prompt §44-45, Fase 2B) — `imagem_url`/
    `link_url` eram URL colada (sem upload real, decisão original de
    escopo). Anexo real de foto/vídeo (2026-09-20): `midia_*` guarda o
    arquivo comprimido (`midia_service`) como blob, mesmo padrão de
    `MaterialOferta` — sem storage de objeto externo configurado no
    projeto ainda."""

    __tablename__ = "post_rede_social"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    usuario_autor_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    texto: Mapped[str] = mapped_column(String)
    imagem_url: Mapped[str | None] = mapped_column(String, nullable=True)
    link_url: Mapped[str | None] = mapped_column(String, nullable=True)
    midia_conteudo: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    midia_tipo_mime: Mapped[str | None] = mapped_column(String, nullable=True)
    midia_tamanho_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
