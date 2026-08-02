from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConfiguracaoNps(Base):
    """Marco configurável de disparo do NPS por assinante (E11-H1)."""

    __tablename__ = "configuracao_nps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, unique=True, index=True)
    dias_apos_reuniao_realizada: Mapped[int] = mapped_column(Integer)
    atualizado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
