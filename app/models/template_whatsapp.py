from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TemplateWhatsApp(Base):
    """Cache local dos templates — status de aprovação visível (E3-H2)."""

    __tablename__ = "template_whatsapp"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    nome: Mapped[str] = mapped_column(String)
    corpo: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)  # aprovado | pendente | rejeitado
    sincronizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
