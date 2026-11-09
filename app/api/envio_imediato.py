"""Envio imediato logo após aprovar uma mensagem ou ativar a cadência.

Antes, o que era aprovado só saía na próxima rodada do cron de envio (GitHub Actions, "a cada 15 min"), que na prática atrasa muito:
em 09/11/2026 houve cerca de 1 h entre rodadas, e quem aprovava um WhatsApp de teste via nada chegar. Aqui, o que já está no horário
sai na hora, pelas mesmas regras do cron (janela de dias úteis e horário, opt-out, CRM, janela de 24 h do WhatsApp). O cron continua
como rede de segurança para o que vencer depois. Uma falha aqui nunca derruba a aprovação: fica no log e o cron tenta de novo."""

import logging

from sqlalchemy.orm import Session

from app.api import deps
from app.core.config import settings
from app.services import envio_service

logger = logging.getLogger(__name__)


def enviar_o_que_ja_venceu(db: Session, tenant_id: str, mensagem_ids: list[int]) -> dict | None:
    if not settings.envio_imediato_ao_aprovar or not mensagem_ids:
        return None
    try:
        whatsapp = deps.resolver_whatsapp_provider(tenant_id, db)
        email = deps.resolver_email_provider(tenant_id, db)
        resultado = envio_service.processar_pendentes(
            db, tenant_id, whatsapp, email, deps.get_email_validation_provider(), somente_mensagem_ids=mensagem_ids
        )
    except Exception:
        db.rollback()
        logger.exception("ENVIO_IMEDIATO_FALHOU tenant=%s mensagens=%s (o cron de envio tenta de novo)", tenant_id, mensagem_ids)
        return None
    logger.info("ENVIO_IMEDIATO tenant=%s mensagens=%s resultado=%s", tenant_id, mensagem_ids, resultado)
    return resultado
