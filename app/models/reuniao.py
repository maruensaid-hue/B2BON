from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Reuniao(Base):
    __tablename__ = "reuniao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("conta.id"))
    decisor_id: Mapped[int] = mapped_column(ForeignKey("decisor.id"))
    vendedor_id: Mapped[str] = mapped_column(String)
    data_hora: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String)  # agendada | realizada | no_show | reagendada
    origem_crm_id: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
