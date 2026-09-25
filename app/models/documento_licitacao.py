from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, LargeBinary, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DocumentoLicitacao(Base):
    """Documento de uma licitação (edital, TR, anexos). Proveniência (§33):
    fonte, URL, hash SHA-256 do arquivo e texto por página, para que cada
    requisito aponte para documento + página + trecho literal."""

    __tablename__ = "documento_licitacao"

    __table_args__ = (UniqueConstraint("licitacao_id", "sha256", name="uq_documento_licitacao_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    licitacao_id: Mapped[int] = mapped_column(ForeignKey("licitacao.id"), index=True)
    tipo: Mapped[str] = mapped_column(String)
    nome_arquivo: Mapped[str] = mapped_column(String)
    tipo_mime: Mapped[str] = mapped_column(String)
    tamanho_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String)
    conteudo: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    paginas_texto: Mapped[list | None] = mapped_column(JSON, nullable=True)
    paginas: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    fonte: Mapped[str] = mapped_column(String)  # UPLOAD | PNCP | URL
    fonte_url: Mapped[str | None] = mapped_column(String, nullable=True)
    status_analise: Mapped[str] = mapped_column(String)  # PENDENTE | ANALISADO | FALHOU | SEM_TEXTO
    analisado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    enviado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
