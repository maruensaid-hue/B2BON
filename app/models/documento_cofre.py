from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DocumentoCofre(Base):
    """Bid Document Vault (§36): certidões, atestados, certificações etc. do
    tenant, com emissor, escopo e validade. Base da matriz de conformidade."""

    __tablename__ = "documento_cofre"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    tipo: Mapped[str] = mapped_column(String)
    nome: Mapped[str] = mapped_column(String)
    emissor: Mapped[str | None] = mapped_column(String, nullable=True)
    escopo: Mapped[str | None] = mapped_column(Text, nullable=True)
    palavras_chave: Mapped[list | None] = mapped_column(JSON, nullable=True)
    valido_desde: Mapped[date | None] = mapped_column(Date, nullable=True)
    valido_ate: Mapped[date | None] = mapped_column(Date, nullable=True)
    nome_arquivo: Mapped[str | None] = mapped_column(String, nullable=True)
    tipo_mime: Mapped[str | None] = mapped_column(String, nullable=True)
    tamanho_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String, nullable=True)
    conteudo: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    enviado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
