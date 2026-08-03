from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Atividade(Base):
    """Timeline de um negócio — liga/nota/reunião/e-mail/tarefa/sistema
    (Onda B). `usuario_id=None` marca eventos automáticos (ex.: oportunidade
    criada pelo PREDATOR, dossiê anexado)."""

    __tablename__ = "atividade"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    negocio_id: Mapped[int] = mapped_column(ForeignKey("negocio.id"), index=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    tipo: Mapped[str] = mapped_column(String)  # ligacao | nota | reuniao | email | tarefa | sistema
    descricao: Mapped[str] = mapped_column(String)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
