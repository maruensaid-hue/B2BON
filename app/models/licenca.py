from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Licenca(Base):
    """Licença de um tenant a um plano — controla franquia/acesso (Onda A)."""

    __tablename__ = "licenca"
    __table_args__ = (UniqueConstraint("tenant_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    plano_id: Mapped[int] = mapped_column(ForeignKey("plano.id"))
    status: Mapped[str] = mapped_column(String)  # ativa | suspensa | expirada
    data_inicio: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    data_expiracao: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Momento em que o usuário se autodeclarou pagador ainda suspenso (raio-X
    # 2026-09-09) — reinicia uma carência própria de 3 dias a partir daqui,
    # independente da carência original de `data_expiracao`.
    declaracao_pagamento_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Idempotência do cron diário de lembrete de cobrança — evita reenviar
    # no mesmo dia se o cron rodar de novo.
    ultimo_lembrete_cobranca_em: Mapped[date | None] = mapped_column(Date, nullable=True)
