from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class InteracaoConta(Base):
    """Sinal de sucesso do cliente sobre uma *conta* (cliente/prospect DE um
    tenant), registrado pelo vendedor/gestor dono da conta — alimenta o MAP
    de contas (score de risco por cliente, distinto do MAP de tenants do
    super_admin em `InteracaoTenant`). Não confundir com `Atividade`, que é
    a timeline de um negócio específico, não da conta como um todo."""

    __tablename__ = "interacao_conta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("conta.id"), index=True)
    # contato | ticket_suporte | reclamacao | feedback_positivo | reuniao_remarcada | mencionou_concorrente
    tipo: Mapped[str] = mapped_column(String)
    descricao: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
