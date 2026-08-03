from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MensagemRedeSocial(Base):
    """Mensageria entre empresas (assinantes) na Rede Social B2B (Onda C) —
    distinta das cadências do PREDATOR, que falam com os prospects de cada
    assinante, não com outros assinantes."""

    __tablename__ = "mensagem_rede_social"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id_remetente: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    tenant_id_destinatario: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    usuario_remetente_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    texto: Mapped[str] = mapped_column(String)
    lida_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
