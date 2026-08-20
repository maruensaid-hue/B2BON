from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Reuniao(Base):
    __tablename__ = "reuniao"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    conta_id: Mapped[int] = mapped_column(ForeignKey("conta.id"))
    decisor_id: Mapped[int] = mapped_column(ForeignKey("decisor.id"))
    vendedor_id: Mapped[str] = mapped_column(String)
    data_hora: Mapped[datetime] = mapped_column(DateTime)
    # horarios_propostos | agendada | realizada | no_show | reagendada | cancelada
    status: Mapped[str] = mapped_column(String)
    origem_crm_id: Mapped[str | None] = mapped_column(String, nullable=True)
    horarios_propostos: Mapped[list] = mapped_column(JSON, default=list)
    horario_confirmado: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    link_reuniao: Mapped[str | None] = mapped_column(String, nullable=True)
    origem_calendario_id: Mapped[str | None] = mapped_column(String, nullable=True)
    reagendado_de_id: Mapped[int | None] = mapped_column(ForeignKey("reuniao.id"), nullable=True)
    lembrete_d1_enviado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    lembrete_h2_enviado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    qualificada_confirmada: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    motivo_qualificacao: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Vídeo + transcrição automática (raio-X: bot de reunião de terceiro,
    # tipo Recall.ai — entra no link do Meet sem depender do Google
    # Workspace de quem organiza). Nulo em toda reunião confirmada antes
    # desta feature, e em toda reunião via StubCalendarProvider (dev/teste).
    bot_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # agendado | gravando | concluida | falhou
    status_transcricao: Mapped[str | None] = mapped_column(String, nullable=True)
    transcricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Resumo gerado por LLM a partir da transcrição — o mesmo texto que vira
    # a Atividade da conta/negócio; guardado aqui pra não precisar reprocessar
    # só pra consultar de novo.
    resumo_ia: Mapped[str | None] = mapped_column(Text, nullable=True)
