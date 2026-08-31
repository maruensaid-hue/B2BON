from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import (
    get_ator_id,
    get_calendar_provider,
    get_crm_provider,
    get_db,
    get_email_provider_do_tenant,
    get_graph_client,
    get_llm_provider,
    get_meeting_bot_provider,
    get_tenant_id,
    get_whatsapp_provider,
)
from app.graph.client import Neo4jClient
from app.llm.base import LLMProvider
from app.models.reuniao import Reuniao
from app.providers.calendar.base import CalendarProvider
from app.providers.channels.email.base import EmailProvider
from app.providers.channels.whatsapp.base import WhatsAppProvider
from app.providers.crm.base import CrmProvider
from app.providers.meeting_bot.base import MeetingBotProvider
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
from app.services import dossie_service, meeting_bot_service, reuniao_service
from app.services.errors import NaoEncontrado

router = APIRouter(prefix="/reunioes", tags=["reunioes"])


@router.get("", response_model=list[ReuniaoListaItemSchema])
def listar_reunioes(
    status: str | None = None,
    conta_id: int | None = None,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[ReuniaoListaItemSchema]:
    return [
        ReuniaoListaItemSchema(**item) for item in reuniao_service.listar(db, tenant_id, status, conta_id)
    ]


@router.post("/processar-lembretes", response_model=ProcessarLembretesResponseSchema)
def processar_lembretes(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
    whatsapp: WhatsAppProvider = Depends(get_whatsapp_provider),
    email: EmailProvider = Depends(get_email_provider_do_tenant),
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
    meeting_bot: MeetingBotProvider = Depends(get_meeting_bot_provider),
) -> ReuniaoSchema:
    """Nenhuma reunião do motor sem registro automático no CRM (E6-H2)."""
    reuniao = reuniao_service.confirmar(
        db, tenant_id, ator_id, reuniao_id, dados.horario_escolhido, calendar, crm, graph
    )
    # Fora do serviço de confirmação de propósito (raio-X: vídeo +
    # transcrição) — a reunião já está confirmada aqui, o bot é
    # melhor-esforço e não pode derrubar a confirmação se falhar.
    meeting_bot_service.agendar_transcricao_pos_confirmacao(db, reuniao, meeting_bot)
    return reuniao


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


@router.post("/{reuniao_id}/reprocessar-transcricao", response_model=ReuniaoSchema)
def reprocessar_transcricao(
    reuniao_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
) -> ReuniaoSchema:
    """Rede de segurança manual (raio-X: vídeo + transcrição) — reroda o
    resumo por IA e a `Atividade` a partir da transcrição já recebida, pra
    quando o resultado do webhook precisar ser regerado. Não busca a
    transcrição de novo no fornecedor: se o webhook nunca chegou (bot não
    respondeu), não há nada aqui pra reprocessar ainda."""
    reuniao: Reuniao = reuniao_service.obter(db, tenant_id, reuniao_id)
    if not reuniao.transcricao:
        raise NaoEncontrado("Esta reunião ainda não tem transcrição registrada.")
    meeting_bot_service.processar_transcricao(db, reuniao, llm, reuniao.transcricao)
    return reuniao


@router.get("/{reuniao_id}/dossie", response_model=DossieSchema)
def obter_dossie(
    reuniao_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
    crm: CrmProvider = Depends(get_crm_provider),
) -> DossieSchema:
    """Dossiê gerado automaticamente e anexado à oportunidade no CRM (E7-H1)."""
    return DossieSchema(**dossie_service.montar_e_anexar(db, tenant_id, reuniao_id, crm))
