from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EmailRecebido(Base):
    """Webmail — caixa de entrada (raio-X 2026-09-24). Criado pelo webhook
    de Inbound Parse do SendGrid quando um cliente responde a um e-mail
    direto (`EmailDireto`) cujo reply-to foi trocado pra um endereço de
    resposta nosso (`resposta_service.gerar_token_resposta`). O conteúdo
    original é sempre retransmitido pro e-mail real do tenant no mesmo
    fluxo — esta tabela é só o registro/cópia, nunca a única fonte da
    mensagem. `decisor_id`/`conta_id` nulos quando o token não resolve
    (nunca descarta o dado por causa disso, só fica sem vínculo)."""

    __tablename__ = "email_recebido"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    decisor_id: Mapped[int | None] = mapped_column(ForeignKey("decisor.id"), nullable=True)
    conta_id: Mapped[int | None] = mapped_column(ForeignKey("conta.id"), nullable=True, index=True)
    remetente_email: Mapped[str] = mapped_column(String)
    assunto: Mapped[str] = mapped_column(String)
    corpo: Mapped[str] = mapped_column(String)
    arquivado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
