from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EventoAprendizado(Base):
    """Learning Loop (Fase 4, §18): recomendação de IA → revisão humana →
    edição/aprovação/rejeição → resultado. Registra EVIDÊNCIA; não afirma
    causalidade."""

    __tablename__ = "evento_aprendizado"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    feature: Mapped[str] = mapped_column(String, index=True)
    tipo: Mapped[str] = mapped_column(String)  # GERADO | APROVADO | EDITADO | REJEITADO | RESULTADO
    entidade_tipo: Mapped[str | None] = mapped_column(String, nullable=True)
    entidade_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usuario_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dados: Mapped[dict] = mapped_column(JSON, default=dict)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
