from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LinkCapturaLead(Base):
    """Link público permanente e reutilizável de um tenant, para captura de
    lead sem login (CTA de anúncio, página de contatos do site etc.) — ao
    contrário de `ConviteVitrine`, nunca expira nem vira "usado": qualquer
    submissão via `codigo` cai como prospect no CRM do `tenant_id` dono."""

    __tablename__ = "link_captura_lead"

    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), primary_key=True)
    codigo: Mapped[str] = mapped_column(String, unique=True, index=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
