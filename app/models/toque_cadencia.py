from sqlalchemy import Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ToqueCadencia(Base):
    """Blueprint de um toque na sequência de uma cadência (E3-H1)."""

    __tablename__ = "toque_cadencia"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    cadencia_id: Mapped[int] = mapped_column(ForeignKey("cadencia.id"))
    ordem: Mapped[int] = mapped_column(Integer)
    canal: Mapped[str] = mapped_column(String)  # whatsapp | email | linkedin
    intervalo_dias_apos_anterior: Mapped[int] = mapped_column(Integer, default=0)
    template_whatsapp_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # Teste A/B por toque (E3-H5): variantes A/B com distribuição controlada.
    ab_teste_habilitado: Mapped[bool] = mapped_column(Boolean, default=False)
