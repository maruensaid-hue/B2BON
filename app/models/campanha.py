from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Campanha(Base):
    """Disparo de e-mail/WhatsApp em massa, deliberadamente separado do
    motor de Cadência (E3) — sem personalização por LLM, sem exigir
    ICP/Oferta configurados, sem consumir a franquia de contas. Decisão
    de escopo do usuário: campanha é uma ferramenta de marketing/anúncio
    em massa, cadência é prospecção individualizada por IA."""

    __tablename__ = "campanha"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    nome: Mapped[str] = mapped_column(String)
    tipo: Mapped[str] = mapped_column(String)  # vendas | marketing
    canais: Mapped[list] = mapped_column(JSON, default=list)  # ["email"], ["whatsapp"], ou ambos
    assunto: Mapped[str | None] = mapped_column(String, nullable=True)
    conteudo_email: Mapped[str | None] = mapped_column(String, nullable=True)
    # Nome do template aprovado na Meta (WhatsAppProvider.listar_templates) —
    # obrigatório se "whatsapp" estiver em canais, mensagem livre fora da
    # janela de 24h não é permitida pela própria plataforma.
    template_whatsapp_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="rascunho")  # rascunho | pronta | enviando | concluida
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class CampanhaDestinatario(Base):
    """Um destinatário snapshot no momento em que entrou na campanha —
    nome/e-mail/telefone copiados na hora (não um join ao vivo), pra a
    campanha continuar íntegra mesmo se o Decisor de origem mudar depois,
    e pra suportar destinatário avulso (sem Decisor nenhum)."""

    __tablename__ = "campanha_destinatario"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    campanha_id: Mapped[int] = mapped_column(ForeignKey("campanha.id"), index=True)
    # Nulo para destinatário de lista colada/avulsa — setado quando veio de
    # um Decisor já cadastrado no CRM.
    decisor_id: Mapped[int | None] = mapped_column(ForeignKey("decisor.id"), nullable=True)
    nome: Mapped[str] = mapped_column(String)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    telefone: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pendente")  # pendente | enviado | falhou | optout
    enviado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    motivo_falha: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
