from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConfiguracaoComunicacao(Base):
    __tablename__ = "configuracao_comunicacao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    tom: Mapped[str] = mapped_column(String)  # formal | consultivo | direto
    restricoes: Mapped[list] = mapped_column(JSON, default=list)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
