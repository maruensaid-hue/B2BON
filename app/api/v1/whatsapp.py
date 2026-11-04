from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import exigir_papel, get_ator_id, get_db, get_tenant_id, get_whatsapp_provider
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


class NovoTemplateSchema(BaseModel):
    nome: str = Field(min_length=1, max_length=512)
    categoria: Literal["UTILITY", "MARKETING"]
    corpo: str = Field(min_length=1, max_length=1024)
    rodape: str | None = Field(default=None, max_length=60)


@router.post("/templates", response_model=TemplateWhatsAppSchema, status_code=201,
             dependencies=[Depends(exigir_papel("super_admin", "admin"))])
def criar_template(
    dados: NovoTemplateSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
    whatsapp: WhatsAppProvider = Depends(get_whatsapp_provider),
) -> TemplateWhatsAppSchema:
    """Cria um modelo de mensagem na conta do WhatsApp da empresa e o envia para aprovação da Meta."""
    return whatsapp_service.criar_template(db, tenant_id, ator_id, whatsapp, dados.nome, dados.categoria, dados.corpo, dados.rodape)
