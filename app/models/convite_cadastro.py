from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConviteCadastro(Base):
    """Código de convite pré-autorizado para cadastro de usuário (Onda A).

    Mesmo padrão de código gerado já usado em
    `indicacao_service.gerar_codigo` (app/services/indicacao_service.py).
    """

    __tablename__ = "convite_cadastro"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    codigo: Mapped[str] = mapped_column(String, unique=True, index=True)
    papel_concedido: Mapped[str] = mapped_column(String)  # admin | user
    criado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    status: Mapped[str] = mapped_column(String, default="disponivel")  # disponivel | usado | revogado | expirado
    validade_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    usado_por_usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
