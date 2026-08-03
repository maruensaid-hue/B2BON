from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class InteracaoTenant(Base):
    """Sinal de sucesso do cliente sobre um *tenant* (assinante da B2B ON),
    registrado manualmente pelo Admin B2B ON — alimenta o score de risco
    de churn do Motor de Alta Performance (Onda D). Não confundir com
    `Atividade` (Onda B), que é sobre os clientes DO tenant, não sobre o
    tenant em si."""

    __tablename__ = "interacao_tenant"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    # contato | ticket_suporte | reclamacao | feedback_positivo | reuniao_remarcada | mencionou_concorrente
    tipo: Mapped[str] = mapped_column(String)
    descricao: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
