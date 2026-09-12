from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SolicitacaoDesconto(Base):
    """Pedido de desconto/vantagem comercial vinculado a um
    `RegistroOportunidade` — só quem é PRIME daquela oportunidade (dono
    do RO ativo) pode criar um pedido; a decisão é sempre manual, do
    admin do tenant raiz da rede (ou super_admin). Mesmo padrão de campos
    de `app/models/aprovacao.py`."""

    __tablename__ = "solicitacao_desconto"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    registro_oportunidade_id: Mapped[int] = mapped_column(ForeignKey("registro_oportunidade.id"))
    solicitante_usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    percentual_solicitado: Mapped[float] = mapped_column(Float)
    justificativa: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String)  # pendente | aprovado | rejeitado
    aprovador_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    motivo_decisao: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    decidido_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
