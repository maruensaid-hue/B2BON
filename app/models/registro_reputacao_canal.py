from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RegistroReputacaoCanal(Base):
    """Contadores diários de entregabilidade por canal — saúde e limiares (E10-H2)."""

    __tablename__ = "registro_reputacao_canal"
    __table_args__ = (UniqueConstraint("tenant_id", "canal", "data"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    canal: Mapped[str] = mapped_column(String)
    data: Mapped[str] = mapped_column(String)  # "YYYY-MM-DD"
    enviados: Mapped[int] = mapped_column(Integer, default=0)
    bounces: Mapped[int] = mapped_column(Integer, default=0)
    spam_reports: Mapped[int] = mapped_column(Integer, default=0)
