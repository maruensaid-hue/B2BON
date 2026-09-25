from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_db, get_llm_provider, get_plan_limits_provider, get_tenant_id
from app.contexts.shared.entitlements import Entitlements
from app.llm.base import LLMProvider
from app.providers.plan_limits.base import PlanLimitsProvider
from app.schemas.inteligencia_rede import (
    AtribuicaoReceitaSchema,
    ConversaoSinalSchema,
    ExplicacaoMatchSchema,
    FitIcpRedeSchema,
    MatchIntentSchema,
    RiscoPipelineSchema,
    SaudeRelacionamentoSchema,
    SinalOportunidadeSchema,
    SugestaoExpansaoSchema,
)
from app.services import intent_service, sinal_oportunidade_service
from app.services.errors import NaoAutorizado

router = APIRouter(prefix="/inteligencia-rede", tags=["inteligencia-rede"])
# C7 (Fase 6): riscos de pipeline e expansão leem só dado de CRM (negócio,
# oferta, atividade). Mesmo path, mas o gate é CRM ou PREDATOR, não só
# PREDATOR. Atribuição de receita continua PREDATOR: depende dos sinais da rede.
router_crm = APIRouter(prefix="/inteligencia-rede", tags=["inteligencia-rede"])


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
    explicacao = sinal_oportunidade_service.explicar_match_com_ia(db, intent_id, tenant_id_candidato, llm, tenant_id_solicitante=tenant_id)
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
    destino: Literal["crm", "predator"] | None = None,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    plan_limits: PlanLimitsProvider = Depends(get_plan_limits_provider),
    db: Session = Depends(get_db),
) -> ConversaoSinalSchema:
    """Network → CRM (conta + negócio) ou → PREDATOR (conta como lead),
    master prompt §51, Fase 8. Reaproveita conta e negócio existentes:
    nenhum sinal gera duplicata. Sem decisor inventado: o vendedor escolhe
    o contato depois. Padrão: CRM se o plano tiver CRM."""
    entitlements = Entitlements(plan_limits, tenant_id)
    destino = destino or ("crm" if entitlements.has_module("crm") else "predator")
    if not entitlements.has_module(destino):
        raise NaoAutorizado(f"Converter para {destino.upper()} exige o módulo {destino.upper()} no plano.")
    return sinal_oportunidade_service.converter_em_oportunidade(db, tenant_id, ator_id, sinal_id, destino)


@router.get("/saude-relacionamentos", response_model=list[SaudeRelacionamentoSchema])
def listar_saude_relacionamentos(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[SaudeRelacionamentoSchema]:
    """Relationship Agent (master prompt §31, Fase 4B)."""
    return sinal_oportunidade_service.listar_saude_relacionamentos(db, tenant_id)


@router_crm.get("/riscos-pipeline", response_model=list[RiscoPipelineSchema])
def listar_riscos_pipeline(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[RiscoPipelineSchema]:
    """Pipeline Agent (master prompt §33, Fase 5C)."""
    return sinal_oportunidade_service.listar_riscos_pipeline(db, tenant_id)


@router.get("/atribuicao-receita", response_model=AtribuicaoReceitaSchema)
def calcular_atribuicao_receita(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> AtribuicaoReceitaSchema:
    """Revenue Agent — Attribution (master prompt §34, §76, Fase 5D)."""
    return sinal_oportunidade_service.calcular_atribuicao_receita(db, tenant_id)


@router_crm.get("/sugestoes-expansao", response_model=list[SugestaoExpansaoSchema])
def sugerir_expansao(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[SugestaoExpansaoSchema]:
    """Revenue Agent — cross-sell/upsell (master prompt §34, Fase 5D)."""
    return sinal_oportunidade_service.sugerir_expansao(db, tenant_id)
