from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PropostaNegocio(Base):
    """Proposta comercial anexada a um negócio — versionada (v1, v2, v3...),
    mesmo padrão de blob-no-banco do `MaterialOferta` (disco do Render é
    efêmero). `gerada_automaticamente=True` marca as que saíram do gerador
    de PDF (Parte E); nesse caso `enviada_por_usuario_id` fica nulo."""

    __tablename__ = "proposta_negocio"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocio.id"), index=True)
    versao: Mapped[int] = mapped_column(Integer)
    nome_arquivo: Mapped[str] = mapped_column(String)
    tipo_mime: Mapped[str] = mapped_column(String)
    conteudo: Mapped[bytes] = mapped_column(LargeBinary)
    tamanho_bytes: Mapped[int] = mapped_column(Integer)
    gerada_automaticamente: Mapped[bool] = mapped_column(Boolean, default=False)
    enviada_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
