from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConfiguracaoCanal(Base):
    """Idade do canal por assinante — insumo da rampa de aquecimento (E10-H1)."""

    __tablename__ = "configuracao_canal"
    __table_args__ = (UniqueConstraint("tenant_id", "canal"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    canal: Mapped[str] = mapped_column(String)
    iniciado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
