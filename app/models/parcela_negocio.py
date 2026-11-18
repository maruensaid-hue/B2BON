from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ParcelaNegocio(Base):
    """Pagamento combinado com o cliente num negócio ganho: quanto e quando ele vai pagar, lançado pelo vendedor (pedido do PO em 18/11/2026).

    É a fonte do quadro "Clientes inadimplentes" do MAP: parcela com `vencimento` no passado (data de Brasília) e `pago_em` nulo está em atraso. O tenant é
    sempre o do negócio; a visibilidade no quadro segue a regra de hierarquia do MAP (`tenant_service.tenant_ids_no_escopo` + vendedor dono do negócio).
    """

    __tablename__ = "parcela_negocio"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocio.id"), index=True)
    numero: Mapped[int] = mapped_column(Integer)  # 1, 2, 3… na ordem de vencimento em que o vendedor lançou
    valor: Mapped[float] = mapped_column(Float)
    vencimento: Mapped[date] = mapped_column(Date, index=True)
    pago_em: Mapped[date | None] = mapped_column(Date, nullable=True)
    observacao: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
