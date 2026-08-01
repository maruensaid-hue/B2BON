from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.decisor import Decisor
from app.schemas.whatsapp import WebhookEmailRequestSchema, WebhookWhatsAppRequestSchema
from app.services import optout_service, resposta_service
from app.services.errors import NaoEncontrado

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_PALAVRAS_OPTOUT = {"sair", "parar", "stop", "cancelar"}


@router.post("/whatsapp")
def webhook_whatsapp(dados: WebhookWhatsAppRequestSchema, db: Session = Depends(get_db)) -> dict:
    """Mensagem recebida do prospect: opt-out por palavra-chave (E9-H2) ou
    resposta que interrompe a cadência (E3-H3)."""
    decisor = db.query(Decisor).filter_by(tenant_id=dados.tenant_id, telefone=dados.telefone).first()
    if decisor is None:
        raise NaoEncontrado("Decisor não encontrado para este telefone.")

    if dados.texto.strip().lower() in _PALAVRAS_OPTOUT:
        return optout_service.processar(db, dados.tenant_id, decisor.id, origem="whatsapp")
    return resposta_service.marcar_resposta(db, dados.tenant_id, decisor.id)


@router.post("/email")
def webhook_email(dados: WebhookEmailRequestSchema, db: Session = Depends(get_db)) -> dict:
    """Integração de inbound-parse do ESP — resposta de e-mail interrompe a
    cadência em todos os canais (E3-H3)."""
    decisor = db.query(Decisor).filter_by(tenant_id=dados.tenant_id, email=dados.email).first()
    if decisor is None:
        raise NaoEncontrado("Decisor não encontrado para este e-mail.")
    return resposta_service.marcar_resposta(db, dados.tenant_id, decisor.id)
