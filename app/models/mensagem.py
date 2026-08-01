from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Mensagem(Base):
    __tablename__ = "mensagem"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    cadencia_id: Mapped[int] = mapped_column(ForeignKey("cadencia.id"))
    decisor_id: Mapped[int] = mapped_column(ForeignKey("decisor.id"))
    canal: Mapped[str] = mapped_column(String)  # whatsapp | email | linkedin
    template_id: Mapped[str | None] = mapped_column(String, nullable=True)
    conteudo: Mapped[str] = mapped_column(String)
    variante_ab: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(
        String
    )  # rascunho | aguardando_aprovacao | aprovado | enviado | falhou
    agendado_para: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    enviado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
