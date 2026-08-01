from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_calendar_provider, get_db, get_llm_provider, get_tenant_id
from app.llm.base import LLMProvider
from app.providers.calendar.base import CalendarProvider
from app.schemas.conversa import DevolverLeadRequestSchema
from app.schemas.reuniao import ProporHorariosRequestSchema, ReuniaoSchema
from app.services import qualificacao_service, reuniao_service

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
