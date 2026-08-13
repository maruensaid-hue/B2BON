from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Atividade(Base):
    """Timeline de uma conta e/ou de um negócio — liga/nota/reunião/e-mail/
    tarefa/sistema. `usuario_id=None` marca eventos totalmente automáticos
    (ex.: disparo de cadência/campanha por cron, sem humano envolvido);
    `usuario_id` setado marca uma ação que um vendedor executou (mesmo que
    quem fez o trabalho pesado tenha sido a IA, como mapear decisores).

    `conta_id`/`negocio_id` são ambos opcionais, mas pelo menos um precisa
    estar setado (validado em `atividade_service.registrar`, não no banco):
    ações em contas ainda sem negócio (Prospecção/MAP) só têm `conta_id`;
    ações específicas de um negócio (mudança de estágio, por exemplo) têm
    os dois, já que todo negócio pertence a uma conta."""

    __tablename__ = "atividade"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    conta_id: Mapped[int | None] = mapped_column(ForeignKey("conta.id"), nullable=True, index=True)
    negocio_id: Mapped[int | None] = mapped_column(ForeignKey("negocio.id"), nullable=True, index=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    tipo: Mapped[str] = mapped_column(String)  # ligacao | nota | reuniao | email | whatsapp | linkedin | tarefa | sistema
    descricao: Mapped[str] = mapped_column(String)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
