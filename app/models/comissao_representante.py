from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ComissaoRepresentante(Base):
    """Uma linha por `PagamentoLicenca` aprovado de um tenant com
    `representante_id` — `pagamento_licenca_id` é único, então reprocessar
    o mesmo webhook nunca duplica a comissão (mesma idempotência de
    `pagamento_licenca_service.confirmar_via_webhook`, que já ignora um
    pagamento já confirmado)."""

    __tablename__ = "comissao_representante"
    __table_args__ = (UniqueConstraint("pagamento_licenca_id"), UniqueConstraint("recebimento_governo_id", "representante_id", "evento"))

    id: Mapped[int] = mapped_column(primary_key=True)
    representante_id: Mapped[int] = mapped_column(ForeignKey("representante.id"), index=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    pagamento_licenca_id: Mapped[int | None] = mapped_column(ForeignKey("pagamento_licenca.id"), nullable=True)
    # B2B ON Government (D-072): comissão por componente, gerada pelo recebimento (gatilho PAYMENT_RECEIVED)
    # ou pela contratação (CONTRACT_SIGNED). Estorno de recebimento já pago vira um CLAWBACK negativo.
    recebimento_governo_id: Mapped[int | None] = mapped_column(ForeignKey("recebimento_governo.id"), nullable=True)
    componente_governo_id: Mapped[int | None] = mapped_column(ForeignKey("componente_contrato_governo.id"), nullable=True, index=True)
    contrato_governo_id: Mapped[int | None] = mapped_column(ForeignKey("contrato_governo.id"), nullable=True, index=True)
    componente_tipo: Mapped[str | None] = mapped_column(String, nullable=True)
    base_calculo: Mapped[float | None] = mapped_column(Float, nullable=True)
    taxa: Mapped[float | None] = mapped_column(Float, nullable=True)
    fracao_divisao: Mapped[float | None] = mapped_column(Float, nullable=True)
    numero_renovacao: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evento: Mapped[str | None] = mapped_column(String, nullable=True)  # ACCRUAL | CLAWBACK
    valor_comissao: Mapped[float] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String, default="calculada")  # calculada | paga | falhou | estornada | a_compensar
    motivo_falha: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    pago_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
