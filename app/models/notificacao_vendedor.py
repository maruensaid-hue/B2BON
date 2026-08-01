from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NotificacaoVendedor(Base):
    """Acionamento do vendedor + medição de SLA até o primeiro contato (E5-H3)."""

    __tablename__ = "notificacao_vendedor"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    conversa_id: Mapped[int] = mapped_column(ForeignKey("conversa_qualificacao.id"))
    vendedor_id: Mapped[str] = mapped_column(String)
    resumo: Mapped[str] = mapped_column(String)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    primeiro_contato_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
