from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import (
    get_ator_id,
    get_calendar_provider,
    get_db,
    get_email_provider,
    get_llm_provider,
    get_tenant_id,
    get_whatsapp_provider,
)
from app.llm.base import LLMProvider
from app.providers.calendar.base import CalendarProvider
from app.providers.channels.email.base import EmailProvider
from app.providers.channels.whatsapp.base import WhatsAppProvider
from app.schemas.conversa import DevolverLeadRequestSchema
from app.schemas.nps import PesquisaNpsSchema
from app.schemas.reuniao import ProporHorariosRequestSchema, ReuniaoSchema
from app.services import nps_service, qualificacao_service, reuniao_service

router = APIRouter(prefix="/decisores", tags=["decisores"])


@router.post("/{decisor_id}/reunioes/propor", response_model=ReuniaoSchema, status_code=201)
def propor_horarios(
    decisor_id: int,
    dados: ProporHorariosRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
    calendar: CalendarProvider = Depends(get_calendar_provider),
) -> ReuniaoSchema:
    return reuniao_service.propor_horarios(
        db, tenant_id, ator_id, decisor_id, dados.vendedor_id, dados.duracao_minutos, calendar
    )


@router.post("/{decisor_id}/devolver")
def devolver_lead(
    decisor_id: int,
    dados: DevolverLeadRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
) -> dict:
    """Devolução do lead à cadência de nutrição adequada ao motivo (E7-H2)."""
    return qualificacao_service.devolver(
        db, tenant_id, ator_id, decisor_id, dados.motivo, dados.cadencia_nutricao_id, llm
    )


@router.post("/{decisor_id}/marco-entrega", response_model=PesquisaNpsSchema, status_code=201)
def marcar_entrega_concluida(
    decisor_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
    whatsapp: WhatsAppProvider = Depends(get_whatsapp_provider),
    email: EmailProvider = Depends(get_email_provider),
) -> PesquisaNpsSchema:
    """Marco manual "entrega concluída" — dispara NPS imediatamente (E11-H1)."""
    return nps_service.marcar_entrega_concluida(db, tenant_id, ator_id, decisor_id, whatsapp, email)
