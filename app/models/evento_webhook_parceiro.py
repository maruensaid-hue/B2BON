from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EventoWebhookParceiro(Base):
    """Fila/outbox de entrega (Fase 2 da hierarquia, raio-X) — o cron
    `POST /cron/disparar-webhooks-parceiros` processa o que está devido
    (`proxima_tentativa_em`), com backoff em `tentativas` até desistir
    (`desistido_em`). `payload_json` guarda o corpo já serializado — o
    mesmo bytes exato precisa ser reenviado em cada tentativa pra bater
    com a assinatura HMAC calculada uma vez na criação."""

    __tablename__ = "evento_webhook_parceiro"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    assinatura_id: Mapped[int] = mapped_column(ForeignKey("assinatura_webhook_parceiro.id"), index=True)
    tipo_evento: Mapped[str] = mapped_column(String)
    payload_json: Mapped[str] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    tentativas: Mapped[int] = mapped_column(Integer, default=0)
    proxima_tentativa_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    entregue_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    desistido_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
