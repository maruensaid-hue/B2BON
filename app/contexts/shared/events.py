"""Eventos de domínio (Fase 2, Master Prompt §77) — contrato + outbox.

- `publicar(db, ...)` grava o evento em `evento_dominio` na mesma sessão
  (flush, sem commit), no mesmo padrão de `auditoria_service.registrar`:
  quem chama faz o commit junto com a mudança de negócio. Se a
  transação falhar, o evento some junto — nunca há evento sem dado.
- `inscrever(tipo, handler)` registra consumidores in-process.
- `processar_pendentes(db)` entrega os eventos ainda não processados aos
  handlers, fora do caminho da requisição (cron, Fase 3). Falha de um
  handler conta tentativa e guarda o erro; o evento fica para a próxima
  rodada até `MAX_TENTATIVAS`.
"""

import logging
import uuid
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.contexts.shared.canonical.base import DataClassification
from app.core.observability import correlation_id_atual
from app.models.evento_dominio import EventoDominio

logger = logging.getLogger(__name__)

MAX_TENTATIVAS = 5


class TipoEvento(StrEnum):
    OPPORTUNITY_CREATED = "OpportunityCreated"
    OPPORTUNITY_STAGE_CHANGED = "OpportunityStageChanged"
    MEETING_COMPLETED = "MeetingCompleted"
    MESSAGE_APPROVED = "MessageApproved"
    CUSTOMER_CREATED = "CustomerCreated"
    CUSTOMER_AT_RISK = "CustomerAtRisk"
    CHURN_PREDICTED = "ChurnPredicted"
    REMEDIATION_CREATED = "RemediationCreated"
    INTENT_CREATED = "IntentCreated"
    BUSINESS_MATCH_CREATED = "BusinessMatchCreated"
    BID_DISCOVERED = "BidDiscovered"
    BID_ANALYZED = "BidAnalyzed"
    PROCUREMENT_DEMAND_CREATED = "ProcurementDemandCreated"
    PROCUREMENT_PLAN_UPDATED = "ProcurementPlanUpdated"
    PROCUREMENT_PROCESS_CREATED = "ProcurementProcessCreated"
    CONTRACT_EXPIRING = "ContractExpiring"
    SUPPLIER_RISK_DETECTED = "SupplierRiskDetected"
    AI_RECOMMENDATION_CREATED = "AIRecommendationCreated"
    AI_RECOMMENDATION_ACCEPTED = "AIRecommendationAccepted"
    AI_RECOMMENDATION_REJECTED = "AIRecommendationRejected"


class EventoDominioDTO(BaseModel):
    model_config = ConfigDict(frozen=True)

    evento_id: str
    tipo: str
    versao: int = 1
    tenant_id: str
    agregado_tipo: str
    agregado_id: str
    ator_id: str | None = None
    classificacao: DataClassification = DataClassification.INTERNAL
    correlation_id: str | None = None
    payload: dict = Field(default_factory=dict)
    ocorrido_em: datetime | None = None


Handler = Callable[[Session, EventoDominioDTO], None]
_handlers: dict[str, list[Handler]] = defaultdict(list)


def inscrever(tipo: TipoEvento | str, handler: Handler) -> None:
    """Idempotente: inscrever o mesmo handler duas vezes não duplica entrega."""
    if handler not in _handlers[str(tipo)]:
        _handlers[str(tipo)].append(handler)


def cancelar_inscricoes() -> None:
    """Só para testes: limpa o registro de handlers."""
    _handlers.clear()


def publicar(
    db: Session,
    tipo: TipoEvento,
    tenant_id: str,
    agregado_tipo: str,
    agregado_id: str | int,
    payload: dict | None = None,
    *,
    ator_id: str | None = None,
    classificacao: DataClassification = DataClassification.INTERNAL,
    correlation_id: str | None = None,
) -> EventoDominio:
    evento = EventoDominio(
        evento_id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        tipo=str(tipo),
        versao=1,
        agregado_tipo=agregado_tipo,
        agregado_id=str(agregado_id),
        ator_id=ator_id,
        classificacao=str(classificacao),
        correlation_id=correlation_id or correlation_id_atual(),
        payload=payload or {},
        tentativas=0,
    )
    db.add(evento)
    db.flush()
    return evento


def _dto(evento: EventoDominio) -> EventoDominioDTO:
    return EventoDominioDTO(
        evento_id=evento.evento_id,
        tipo=evento.tipo,
        versao=evento.versao,
        tenant_id=evento.tenant_id,
        agregado_tipo=evento.agregado_tipo,
        agregado_id=evento.agregado_id,
        ator_id=evento.ator_id,
        classificacao=DataClassification(evento.classificacao),
        correlation_id=evento.correlation_id,
        payload=evento.payload or {},
        ocorrido_em=evento.ocorrido_em,
    )


def processar_pendentes(db: Session, limite: int = 200) -> dict:
    pendentes = (
        db.query(EventoDominio)
        .filter(EventoDominio.processado_em.is_(None), EventoDominio.tentativas < MAX_TENTATIVAS)
        .order_by(EventoDominio.id)
        .limit(limite)
        .all()
    )
    processados = falhas = 0
    for evento in pendentes:
        dto = _dto(evento)
        try:
            for handler in _handlers.get(evento.tipo, []):
                handler(db, dto)
        except Exception as erro:  # noqa: BLE001 — um handler ruim não pode travar a fila
            evento.tentativas += 1
            evento.ultimo_erro = f"{type(erro).__name__}: {erro}"[:500]
            falhas += 1
            logger.exception("Falha ao processar evento %s (%s)", evento.evento_id, evento.tipo)
        else:
            evento.processado_em = datetime.now(UTC)
            processados += 1
    db.commit()
    return {"processados": processados, "falhas": falhas}
