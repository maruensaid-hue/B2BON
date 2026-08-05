from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import (
    get_ator_id,
    get_calendar_provider,
    get_crm_provider,
    get_db,
    get_email_provider,
    get_graph_client,
    get_tenant_id,
    get_whatsapp_provider,
)
from app.graph.client import Neo4jClient
from app.providers.calendar.base import CalendarProvider
from app.providers.channels.email.base import EmailProvider
from app.providers.channels.whatsapp.base import WhatsAppProvider
from app.providers.crm.base import CrmProvider
from app.schemas.dossie import DossieSchema
from app.schemas.reuniao import (
    ConfirmarQualificacaoRequestSchema,
    ConfirmarReuniaoRequestSchema,
    MarcarResultadoReuniaoRequestSchema,
    ProcessarLembretesResponseSchema,
    ReagendarReuniaoRequestSchema,
    ReuniaoListaItemSchema,
    ReuniaoSchema,
)
from app.services import dossie_service, reuniao_service

router = APIRouter(prefix="/reunioes", tags=["reunioes"])


@router.get("", response_model=list[ReuniaoListaItemSchema])
def listar_reunioes(
    status: str | None = None,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[ReuniaoListaItemSchema]:
    return [ReuniaoListaItemSchema(**item) for item in reuniao_service.listar(db, tenant_id, status)]


@router.post("/processar-lembretes", response_model=ProcessarLembretesResponseSchema)
def processar_lembretes(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
    whatsapp: WhatsAppProvider = Depends(get_whatsapp_provider),
    email: EmailProvider = Depends(get_email_provider),
) -> ProcessarLembretesResponseSchema:
    """Dispatcher de lembretes D-1/H-2 — chamado por cron externo (E6-H1)."""
    return ProcessarLembretesResponseSchema(**reuniao_service.processar_lembretes(db, tenant_id, whatsapp, email))


@router.get("/reagendar/{token}", response_model=ReuniaoSchema)
def obter_reagendamento(token: str, db: Session = Depends(get_db)) -> ReuniaoSchema:
    """Endpoint público — o lead vê os dados da reunião a partir do link recebido."""
    return reuniao_service.obter_por_token(db, token)


@router.post("/reagendar/{token}", response_model=ReuniaoSchema)
def reagendar(
    token: str,
    dados: ReagendarReuniaoRequestSchema,
    db: Session = Depends(get_db),
    calendar: CalendarProvider = Depends(get_calendar_provider),
    crm: CrmProvider = Depends(get_crm_provider),
    graph: Neo4jClient = Depends(get_graph_client),
) -> ReuniaoSchema:
    """Reagendamento pelo próprio lead — endpoint público, sem X-Tenant-Id (E6-H1)."""
    return reuniao_service.reagendar_por_token(db, token, dados.novo_horario, calendar, crm, graph)


@router.post("/{reuniao_id}/confirmar", response_model=ReuniaoSchema)
def confirmar(
    reuniao_id: int,
    dados: ConfirmarReuniaoRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
    calendar: CalendarProvider = Depends(get_calendar_provider),
    crm: CrmProvider = Depends(get_crm_provider),
    graph: Neo4jClient = Depends(get_graph_client),
) -> ReuniaoSchema:
    """Nenhuma reunião do motor sem registro automático no CRM (E6-H2)."""
    return reuniao_service.confirmar(
        db, tenant_id, ator_id, reuniao_id, dados.horario_escolhido, calendar, crm, graph
    )


@router.post("/{reuniao_id}/marcar-resultado", response_model=ReuniaoSchema)
def marcar_resultado(
    reuniao_id: int,
    dados: MarcarResultadoReuniaoRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ReuniaoSchema:
    return reuniao_service.marcar_resultado(db, tenant_id, ator_id, reuniao_id, dados.status)


@router.post("/{reuniao_id}/confirmar-qualificacao", response_model=ReuniaoSchema)
def confirmar_qualificacao(
    reuniao_id: int,
    dados: ConfirmarQualificacaoRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ReuniaoSchema:
    """Prompt pós-reunião de 1 toque — feedback alimenta o scoring (E6-H3)."""
    return reuniao_service.confirmar_qualificacao(
        db, tenant_id, ator_id, reuniao_id, dados.qualificada, dados.motivo
    )


@router.get("/{reuniao_id}/dossie", response_model=DossieSchema)
def obter_dossie(
    reuniao_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
    crm: CrmProvider = Depends(get_crm_provider),
) -> DossieSchema:
    """Dossiê gerado automaticamente e anexado à oportunidade no CRM (E7-H1)."""
    return DossieSchema(**dossie_service.montar_e_anexar(db, tenant_id, reuniao_id, crm))
