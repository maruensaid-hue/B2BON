from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConfiguracaoNotificacao(Base):
    """Vendedor a notificar em tempo real (E5-H3)."""

    __tablename__ = "configuracao_notificacao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    vendedor_id: Mapped[str] = mapped_column(String)
    vendedor_telefone: Mapped[str] = mapped_column(String)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
