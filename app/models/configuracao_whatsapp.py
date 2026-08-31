from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.crypto import TextoCriptografado
from app.db.base import Base


class ConfiguracaoWhatsApp(Base):
    """Número de WhatsApp Business próprio do tenant (raio-X de produção,
    endurecido em 2026-08-27) — sem isto, todo tenant compartilhava o
    mesmo número global (`settings.whatsapp_access_token`, hoje sem
    fallback nenhum), e um cliente prospectando mal podia fazer a Meta
    restringir o número de todo mundo junto. Tenant sem linha aqui não
    consegue mais mandar WhatsApp (`resolver_whatsapp_provider` cai em
    `WhatsAppDesativadoProvider` em produção) até configurar a própria
    conta.

    Credenciais Meta (access_token/phone_number_id/business_account_id)
    ficam criptografadas em repouso (`TextoCriptografado`, achado de
    segurança do raio-X de compliance) — o ORM continua lendo/gravando
    texto puro em memória, só o banco vê o valor cifrado."""

    __tablename__ = "configuracao_whatsapp"
    __table_args__ = (UniqueConstraint("tenant_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    access_token: Mapped[str] = mapped_column(TextoCriptografado)
    phone_number_id: Mapped[str] = mapped_column(TextoCriptografado)
    business_account_id: Mapped[str] = mapped_column(TextoCriptografado)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
