from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_tenant_id, get_whatsapp_provider
from app.providers.channels.whatsapp.base import WhatsAppProvider
from app.schemas.whatsapp import TemplateWhatsAppSchema
from app.services import whatsapp_service

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])


@router.get("/templates", response_model=list[TemplateWhatsAppSchema])
def listar_templates(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
    whatsapp: WhatsAppProvider = Depends(get_whatsapp_provider),
) -> list[TemplateWhatsAppSchema]:
    return whatsapp_service.sincronizar_templates(db, tenant_id, whatsapp)
