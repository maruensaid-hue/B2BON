from sqlalchemy import Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RegistroEnvioDiario(Base):
    """Contador de envios do dia por canal — bloqueio de burla da rampa (E10-H1)."""

    __tablename__ = "registro_envio_diario"
    __table_args__ = (UniqueConstraint("tenant_id", "canal", "data"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    canal: Mapped[str] = mapped_column(String)
    data: Mapped[str] = mapped_column(String)  # "YYYY-MM-DD"
    quantidade_enviada: Mapped[int] = mapped_column(Integer, default=0)
