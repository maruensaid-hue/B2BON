from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PagamentoLicenca(Base):
    """Tentativa de pagamento (Mercado Pago) para formalizar a licença de
    um tenant nascido do cadastro self-service (convite-vitrine com
    escolha de plano). `external_reference` da preference do MP aponta
    para `str(id)` desta linha — é assim que o webhook casa o pagamento
    de volta ao tenant/plano certos."""

    __tablename__ = "pagamento_licenca"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    plano_id: Mapped[int] = mapped_column(ForeignKey("plano.id"))
    preferencia_id_externo: Mapped[str] = mapped_column(String)
    pagamento_id_externo: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String)  # pendente | aprovado | rejeitado
    valor: Mapped[float] = mapped_column(Float)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    confirmado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
