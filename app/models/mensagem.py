from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Mensagem(Base):
    __tablename__ = "mensagem"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    # Nullable: pedidos de indicação (E11-H2) são mensagens avulsas, fora
    # do conceito de cadência multicanal.
    cadencia_id: Mapped[int | None] = mapped_column(ForeignKey("cadencia.id"), nullable=True)
    decisor_id: Mapped[int] = mapped_column(ForeignKey("decisor.id"))
    # Rastreia de qual toque do blueprint esta mensagem veio — usado na
    # ativação da cadência para calcular agendado_para (ordem/intervalo).
    toque_cadencia_id: Mapped[int | None] = mapped_column(ForeignKey("toque_cadencia.id"), nullable=True)
    canal: Mapped[str] = mapped_column(String)  # whatsapp | email | linkedin
    template_id: Mapped[str | None] = mapped_column(String, nullable=True)
    conteudo: Mapped[str] = mapped_column(String)
    variante_ab: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(
        String
    )  # rascunho | aguardando_aprovacao | aprovado | enviado | falhou | cancelado
    agendado_para: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    enviado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    motivo_falha: Mapped[str | None] = mapped_column(String, nullable=True)
    tentativas_envio: Mapped[int] = mapped_column(Integer, default=0)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
