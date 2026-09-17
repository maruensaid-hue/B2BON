from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_db, get_llm_provider, get_tenant_id
from app.llm.base import LLMProvider
from app.schemas.inteligencia_rede import (
    ConversaoSinalSchema,
    ExplicacaoMatchSchema,
    FitIcpRedeSchema,
    MatchIntentSchema,
    SinalOportunidadeSchema,
)
from app.services import intent_service, sinal_oportunidade_service

router = APIRouter(prefix="/inteligencia-rede", tags=["inteligencia-rede"])


@router.get("/fit-icp", response_model=list[FitIcpRedeSchema])
def listar_fit_icp_rede(
    icp_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[FitIcpRedeSchema]:
    """ICP Agent — fit ICP×Rede (master prompt §25, §60, Fase 3B)."""
    return sinal_oportunidade_service.listar_fit_icp_rede(db, tenant_id, icp_id)


@router.get("/intents/{intent_id}/matches", response_model=list[MatchIntentSchema])
def listar_matches_intent(
    intent_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[MatchIntentSchema]:
    """Intent Agent + Match Engine (master prompt §26, §48-49, Fase 3C)."""
    intent_service.obter_visivel(db, tenant_id, intent_id)
    return sinal_oportunidade_service.sugerir_fornecedores_para_intent(db, tenant_id, intent_id)


@router.post("/intents/{intent_id}/matches/{tenant_id_candidato}/explicar-com-ia", response_model=ExplicacaoMatchSchema)
def explicar_match_com_ia(
    intent_id: int,
    tenant_id_candidato: str,
    tenant_id: str = Depends(get_tenant_id),
    llm: LLMProvider = Depends(get_llm_provider),
    db: Session = Depends(get_db),
) -> ExplicacaoMatchSchema:
    intent_service.obter_visivel(db, tenant_id, intent_id)
    explicacao = sinal_oportunidade_service.explicar_match_com_ia(db, intent_id, tenant_id_candidato, llm)
    return {"explicacao": explicacao}


@router.post("/sinais/gerar", response_model=list[SinalOportunidadeSchema])
def gerar_sinais(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[SinalOportunidadeSchema]:
    """Opportunity Agent — gera/atualiza sinais (master prompt §28, §50,
    Fase 3D). On-demand, sem cron novo."""
    return sinal_oportunidade_service.gerar_sinais(db, tenant_id)


@router.get("/sinais", response_model=list[SinalOportunidadeSchema])
def listar_sinais(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[SinalOportunidadeSchema]:
    return sinal_oportunidade_service.listar(db, tenant_id)


@router.post("/sinais/{sinal_id}/visto", response_model=SinalOportunidadeSchema)
def marcar_sinal_visto(
    sinal_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> SinalOportunidadeSchema:
    return sinal_oportunidade_service.marcar_visto(db, tenant_id, sinal_id)


@router.post("/sinais/{sinal_id}/descartar", response_model=SinalOportunidadeSchema)
def descartar_sinal(
    sinal_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> SinalOportunidadeSchema:
    return sinal_oportunidade_service.descartar(db, tenant_id, ator_id, sinal_id)


@router.post("/sinais/{sinal_id}/converter", response_model=ConversaoSinalSchema)
def converter_sinal_em_oportunidade(
    sinal_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ConversaoSinalSchema:
    """Signal → CRM (master prompt §51, Fase 3D) — cria/reaproveita a
    Conta a partir do sinal; o humano fecha o Negócio manualmente no
    CRM (ver decisão de escopo 5 do plano — sem decisor inventado)."""
    return sinal_oportunidade_service.converter_em_oportunidade(db, tenant_id, ator_id, sinal_id)
