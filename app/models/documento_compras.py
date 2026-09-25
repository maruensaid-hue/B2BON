from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DocumentoCompras(Base):
    """Document Intelligence (§48): documento com hash, fonte, texto por página e achados com evidência.

    Dado CONFIDENTIAL do tenant comprador (barreira Buy/Sell, Fase 10)."""

    __tablename__ = "documento_compras"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    processo_id: Mapped[int | None] = mapped_column(ForeignKey("processo_contratacao.id"), nullable=True)
    contrato_id: Mapped[int | None] = mapped_column(ForeignKey("contrato_compra.id"), nullable=True)
    tipo: Mapped[str] = mapped_column(String)
    nome_arquivo: Mapped[str] = mapped_column(String)
    tipo_mime: Mapped[str] = mapped_column(String)
    tamanho_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String)
    conteudo: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    paginas_texto: Mapped[list | None] = mapped_column(JSON, nullable=True)
    paginas: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    fonte: Mapped[str] = mapped_column(String)
    fonte_url: Mapped[str | None] = mapped_column(String, nullable=True)
    classificacao: Mapped[str] = mapped_column(String)
    achados: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status_analise: Mapped[str] = mapped_column(String)
    enviado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
