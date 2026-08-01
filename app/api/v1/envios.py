from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_email_provider, get_tenant_id, get_whatsapp_provider
from app.providers.channels.email.base import EmailProvider
from app.providers.channels.whatsapp.base import WhatsAppProvider
from app.services import envio_service

router = APIRouter(prefix="/envios", tags=["envios"])


@router.post("/processar")
def processar_envios(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
    whatsapp: WhatsAppProvider = Depends(get_whatsapp_provider),
    email: EmailProvider = Depends(get_email_provider),
) -> dict:
    """Dispatcher de envio — chamado por cron externo (Onda 2)."""
    return envio_service.processar_pendentes(db, tenant_id, whatsapp, email)
