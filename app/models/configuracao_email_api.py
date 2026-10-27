from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.crypto import TextoCriptografado
from app.db.base import Base


class ConfiguracaoEmailApi(Base):
    """Envio de e-mail por API do serviço de envio próprio do cliente: com ele o relatório mede entrega, bounce, spam e abertura de verdade (com conta
    SMTP o servidor só confirma que aceitou a mensagem). Tem prioridade sobre a conta SMTP (`ConfiguracaoEmailSmtp`) quando existe.

    `chave_api` e `chave_webhook` ficam cifradas em repouso (mesmo padrão de `ConfiguracaoEmailSmtp`). `chave_webhook` é a chave pública de verificação do
    aviso de eventos do serviço: sem ela o sistema não aceita os retornos de entrega/bounce desse cliente, porque não teria como saber se vieram mesmo do
    serviço (qualquer um poderia forjá-los)."""

    __tablename__ = "configuracao_email_api"
    __table_args__ = (UniqueConstraint("tenant_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    chave_api: Mapped[str] = mapped_column(TextoCriptografado)
    remetente_email: Mapped[str] = mapped_column(String)
    remetente_nome: Mapped[str | None] = mapped_column(String, nullable=True)
    chave_webhook: Mapped[str | None] = mapped_column(TextoCriptografado, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
