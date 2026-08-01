from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class QualificacaoScore(Base):
    __tablename__ = "qualificacao_score"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("conta.id"))
    decisor_id: Mapped[int] = mapped_column(ForeignKey("decisor.id"))
    score_total: Mapped[float] = mapped_column(Float)
    criterios: Mapped[dict] = mapped_column(JSON, default=dict)  # decomposição S.H.A.R.K.
    limiar_configurado: Mapped[float] = mapped_column(Float)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
