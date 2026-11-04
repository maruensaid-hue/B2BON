from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.crypto import TextoCriptografado
from app.db.base import Base


class ConfiguracaoWhatsApp(Base):
    """Número de WhatsApp Business próprio do tenant (raio-X de produção,
    endurecido em 2026-08-27) — sem isto, todo tenant compartilhava o
    mesmo número global (`settings.whatsapp_access_token`, hoje sem
    fallback nenhum), e um cliente prospectando mal podia fazer a Meta
    restringir o número de todo mundo junto. Tenant sem linha aqui não
    consegue mais mandar WhatsApp (`resolver_whatsapp_provider` cai em
    `WhatsAppDesativadoProvider` em produção) até configurar a própria
    conta.

    Credenciais Meta (access_token/phone_number_id/business_account_id)
    ficam criptografadas em repouso (`TextoCriptografado`, achado de
    segurança do raio-X de compliance) — o ORM continua lendo/gravando
    texto puro em memória, só o banco vê o valor cifrado."""

    __tablename__ = "configuracao_whatsapp"
    __table_args__ = (UniqueConstraint("tenant_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, index=True)
    access_token: Mapped[str] = mapped_column(TextoCriptografado)
    phone_number_id: Mapped[str] = mapped_column(TextoCriptografado)
    business_account_id: Mapped[str] = mapped_column(TextoCriptografado)
    # Como o número foi conectado: meta_conectar (botão "Conectar com a Meta", cadastro incorporado) | manual (IDs e token colados).
    origem_conexao: Mapped[str | None] = mapped_column(String, nullable=True)
    # PIN de 6 dígitos da verificação em duas etapas, criado no registro do número pela conexão com a Meta (preciso para registrar de novo).
    pin_registro: Mapped[str | None] = mapped_column(TextoCriptografado, nullable=True)
    # O que a Meta informou na última conexão/teste (sem segredo): mostrado na tela como prova de que está ligado.
    numero_exibicao: Mapped[str | None] = mapped_column(String, nullable=True)
    nome_verificado: Mapped[str | None] = mapped_column(String, nullable=True)
    qualidade: Mapped[str | None] = mapped_column(String, nullable=True)
    # Quando o token vence, segundo a Meta (debug_token). Nulo = sem prazo (ou ainda não consultado). O token do cadastro incorporado
    # vence em 60 dias: a tela avisa antes e "Reconectar com a Meta" renova.
    token_expira_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Direct Send (envio sem template, categoria utilidade): o admin declara que a conta está habilitada no WhatsApp Manager. Se a
    # Meta recusar a conta (erro 100 de Direct Send), o sistema desliga sozinho e guarda o motivo.
    direct_send_habilitado: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    direct_send_motivo_desligado: Mapped[str | None] = mapped_column(String, nullable=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    atualizado_em: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
