from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ComissaoRepresentante(Base):
    """Uma linha por `PagamentoLicenca` aprovado de um tenant com
    `representante_id` — `pagamento_licenca_id` é único, então reprocessar
    o mesmo webhook nunca duplica a comissão (mesma idempotência de
    `pagamento_licenca_service.confirmar_via_webhook`, que já ignora um
    pagamento já confirmado)."""

    __tablename__ = "comissao_representante"
    __table_args__ = (UniqueConstraint("pagamento_licenca_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    representante_id: Mapped[int] = mapped_column(ForeignKey("representante.id"), index=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    pagamento_licenca_id: Mapped[int] = mapped_column(ForeignKey("pagamento_licenca.id"))
    valor_comissao: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String, default="calculada")  # calculada | paga | falhou
    motivo_falha: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    pago_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
