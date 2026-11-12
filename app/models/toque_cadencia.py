from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ToqueCadencia(Base):
    """Blueprint de um toque na sequência de uma cadência (E3-H1)."""

    __tablename__ = "toque_cadencia"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    cadencia_id: Mapped[int] = mapped_column(ForeignKey("cadencia.id"))
    ordem: Mapped[int] = mapped_column(Integer)
    canal: Mapped[str] = mapped_column(String)  # whatsapp | email | linkedin
    intervalo_dias_apos_anterior: Mapped[int] = mapped_column(Integer, default=0)
    template_whatsapp_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # Teste A/B por toque (E3-H5): variantes A/B com distribuição controlada.
    ab_teste_habilitado: Mapped[bool] = mapped_column(Boolean, default=False)
    # Toque de WhatsApp SEM template (Direct Send da Meta, categoria utilidade). Só com o risco aceito na cadência por um admin
    # (`Cadencia.direct_send_aceito_por`) e a conta habilitada; o texto passa pela checagem de conteúdo promocional antes de sair.
    whatsapp_sem_template: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    # Texto fixo (opcional): quando preenchido, a geração usa este texto em vez de pedir à IA. Aceita os marcadores das Campanhas — [Nome]
    # (primeiro nome), [Nome completo] e [Empresa] — trocados pelos dados de cada contato na geração. `assunto_fixo` é obrigatório no e-mail
    # com texto fixo e ignorado nos outros canais. Sem texto fixo, nada muda: a IA escreve o toque.
    texto_fixo: Mapped[str | None] = mapped_column(Text, nullable=True)
    assunto_fixo: Mapped[str | None] = mapped_column(String, nullable=True)
