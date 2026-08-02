from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PesquisaNps(Base):
    """Medição de NPS disparada por marco de entrega (E11-H1)."""

    __tablename__ = "pesquisa_nps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("conta.id"))
    decisor_id: Mapped[int] = mapped_column(ForeignKey("decisor.id"))
    marco: Mapped[str] = mapped_column(String)  # dias_apos_reuniao | entrega_concluida
    nota: Mapped[int | None] = mapped_column(Integer, nullable=True)
    classificacao: Mapped[str | None] = mapped_column(String, nullable=True)  # promotor | neutro | detrator
    enviada_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    respondida_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
