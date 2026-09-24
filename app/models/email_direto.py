from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EmailDireto(Base):
    """Webmail — e-mail pessoal do vendedor pra um decisor do CRM (raio-X
    2026-09-24), distinto de `Mensagem` (proposta de IA pra cadência,
    sempre passa pela fila de aprovação). Aqui o vendedor já escreveu e
    revisou o texto sozinho — envio é síncrono, sem fila. Sem rastreio
    assíncrono de abertura/bounce nesta entrega (isso hoje é amarrado a
    `custom_args` que correlaciona de volta com `Mensagem`, não com
    esta tabela nova) — só a falha SÍNCRONA do provider é capturada."""

    __tablename__ = "email_direto"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenant.id"), index=True)
    remetente_usuario_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    decisor_id: Mapped[int] = mapped_column(ForeignKey("decisor.id"))
    # Denormalizado — evita join pra listar "enviados de uma conta".
    conta_id: Mapped[int] = mapped_column(ForeignKey("conta.id"), index=True)
    assunto: Mapped[str] = mapped_column(String)
    corpo: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)  # enviado | falhou
    motivo_falha: Mapped[str | None] = mapped_column(String, nullable=True)
    enviado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Arquivamento de conversa (raio-X 2026-09-24) — marcado por
    # `email_direto_service.arquivar_conversa`, some das abas
    # Enviados/Recebidos por padrão mas nunca é excluído.
    arquivado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
