from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConfiguracaoQualificacao(Base):
    """Limiar de qualificação configurável por assinante, com padrão
    recomendado (E5-H2)."""

    __tablename__ = "configuracao_qualificacao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    limiar_padrao: Mapped[float] = mapped_column(Float)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
