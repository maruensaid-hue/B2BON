from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConexaoLinkedin(Base):
    """Uma linha do CSV de conexões que o próprio vendedor exportou do
    LinkedIn (recurso oficial "Obter uma cópia dos seus dados") — usado só
    para checar se um decisor encontrado já é conexão dele, nunca para
    automatizar ação nenhuma no LinkedIn."""

    __tablename__ = "conexao_linkedin"
    __table_args__ = (Index("ix_conexao_linkedin_tenant_usuario", "tenant_id", "usuario_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    nome_completo: Mapped[str] = mapped_column(String)
    # Normalizada na gravação (sem protocolo/www/query) para comparação estável.
    url_perfil: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    empresa_atual: Mapped[str | None] = mapped_column(String, nullable=True)
    cargo_atual: Mapped[str | None] = mapped_column(String, nullable=True)
    conectado_em: Mapped[date | None] = mapped_column(Date, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
