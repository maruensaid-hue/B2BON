from datetime import datetime, time

from sqlalchemy import DateTime, Integer, String, Time, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConfiguracaoEnvio(Base):
    """Remetente, assinatura e janela de envio de e-mail por assinante (E3-H3)."""

    __tablename__ = "configuracao_envio"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    remetente_nome: Mapped[str] = mapped_column(String)
    remetente_email: Mapped[str] = mapped_column(String)
    assinatura: Mapped[str] = mapped_column(String, default="")
    horario_inicio: Mapped[time] = mapped_column(Time)
    horario_fim: Mapped[time] = mapped_column(Time)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
