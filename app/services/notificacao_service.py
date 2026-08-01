from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.configuracao_notificacao import ConfiguracaoNotificacao
from app.models.conversa_qualificacao import ConversaQualificacao
from app.models.notificacao_vendedor import NotificacaoVendedor
from app.providers.channels.whatsapp.base import WhatsAppProvider
from app.services import auditoria_service
from app.services.errors import NaoEncontrado


def notificar_vendedor(
    db: Session,
    tenant_id: str,
    conversa: ConversaQualificacao,
    whatsapp: WhatsAppProvider,
    motivo: str,
) -> NotificacaoVendedor:
    """Notificação em tempo real (in-app + WhatsApp do vendedor) com resumo
    do lead (E5-H3). Não passa pelas regras de janela/rampa da Onda 2 — são
    específicas de prospecção externa ao prospect, não de aviso interno."""
    config = db.query(ConfiguracaoNotificacao).filter_by(tenant_id=tenant_id).one_or_none()
    vendedor_id = config.vendedor_id if config else "vendedor-padrao"
    resumo = f"Lead da conta {conversa.conta_id} (decisor {conversa.decisor_id}) — {motivo}."

    notificacao = NotificacaoVendedor(
        tenant_id=tenant_id, conversa_id=conversa.id, vendedor_id=vendedor_id, resumo=resumo
    )
    db.add(notificacao)
    db.flush()

    if config and config.vendedor_telefone:
        whatsapp.enviar_texto_livre(config.vendedor_telefone, resumo)

    auditoria_service.registrar(
        db,
        tenant_id,
        "vendedor_notificado",
        "notificacao_vendedor",
        notificacao.id,
        None,
        {"motivo": motivo},
        conta_id=conversa.conta_id,
    )
    return notificacao


def confirmar_contato(db: Session, tenant_id: str, notificacao_id: int) -> NotificacaoVendedor:
    """SLA visível: tempo entre qualificação e primeiro contato humano (E5-H3)."""
    notificacao = db.query(NotificacaoVendedor).filter_by(id=notificacao_id, tenant_id=tenant_id).one_or_none()
    if notificacao is None:
        raise NaoEncontrado(f"Notificação {notificacao_id} não encontrada")

    if notificacao.primeiro_contato_em is None:
        notificacao.primeiro_contato_em = datetime.now(UTC)
    db.commit()
    db.refresh(notificacao)
    return notificacao
