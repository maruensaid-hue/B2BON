from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FaqItem(Base):
    """Base de FAQ do assinante, alimentada no onboarding (E5-H4)."""

    __tablename__ = "faq_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    pergunta: Mapped[str] = mapped_column(String)
    resposta: Mapped[str] = mapped_column(String)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
