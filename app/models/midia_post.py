from sqlalchemy import ForeignKey, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MidiaPost(Base):
    """Foto/vídeo anexado a um post da Rede Social/Shoal — um post pode
    ter várias linhas (carrossel), mas só quando todas forem foto;
    vídeo é sempre sozinho (`post_rede_social_service.criar` valida
    isso, não o schema). Substitui as colunas `midia_*` que viviam
    direto em `PostRedeSocial` (só suportavam 1 anexo por post)."""

    __tablename__ = "midia_post"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("post_rede_social.id"), index=True)
    ordem: Mapped[int] = mapped_column(Integer)
    conteudo: Mapped[bytes] = mapped_column(LargeBinary)
    tipo_mime: Mapped[str] = mapped_column(String)
    tamanho_bytes: Mapped[int] = mapped_column(Integer)
