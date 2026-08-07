from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConfiguracaoWhatsApp(Base):
    """Número de WhatsApp Business próprio do tenant (raio-X de produção)
    — sem isto, todo tenant compartilhava o mesmo número global
    (`settings.whatsapp_access_token`), e um cliente prospectando mal
    podia fazer a Meta restringir o número de todo mundo junto. Tenant
    sem linha aqui cai no fallback legado (número compartilhado) em
    `get_whatsapp_provider`, até migrar pro próprio."""

    __tablename__ = "configuracao_whatsapp"
    __table_args__ = (UniqueConstraint("tenant_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    access_token: Mapped[str] = mapped_column(String)
    phone_number_id: Mapped[str] = mapped_column(String)
    business_account_id: Mapped[str] = mapped_column(String)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
