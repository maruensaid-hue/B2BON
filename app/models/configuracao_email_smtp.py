from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.crypto import TextoCriptografado
from app.db.base import Base


class ConfiguracaoEmailSmtp(Base):
    """Conta de e-mail (SMTP) própria do tenant (raio-X 2026-08-27) — sem
    isto, todo tenant disparava e-mail de cadência/campanha pelo SendGrid
    compartilhado da própria CyberFort. Tenant sem linha aqui não
    consegue mais disparar e-mail (`resolver_email_provider` cai direto
    em `EmailDesativadoProvider`, sem fallback compartilhado) — precisa
    configurar a própria conta pra funcionar.

    `usuario`/`senha` ficam criptografados em repouso (mesmo padrão de
    `ConfiguracaoWhatsApp`/`TextoCriptografado`) — host/porta não são
    segredo, ficam em texto puro."""

    __tablename__ = "configuracao_email_smtp"
    __table_args__ = (UniqueConstraint("tenant_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    host: Mapped[str] = mapped_column(String)
    porta: Mapped[int] = mapped_column(Integer)
    usuario: Mapped[str] = mapped_column(TextoCriptografado)
    senha: Mapped[str] = mapped_column(TextoCriptografado)
    usar_tls: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
