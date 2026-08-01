from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_db, get_llm_provider, get_plan_limits_provider, get_tenant_id
from app.llm.base import LLMProvider
from app.providers.plan_limits.base import PlanLimitsProvider
from app.schemas.cadencia import (
    AtivarCadenciaResponseSchema,
    CadenciaCreateSchema,
    CadenciaSchema,
    GerarCadenciaRequestSchema,
    GerarCadenciaResponseSchema,
    RelatorioAbTesteSchema,
)
from app.services import ab_teste_service, cadencia_service

router = APIRouter(prefix="/cadencias", tags=["cadencias"])


@router.post("", response_model=CadenciaSchema, status_code=201)
def criar_cadencia(
    dados: CadenciaCreateSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> CadenciaSchema:
    return cadencia_service.criar(db, tenant_id, ator_id, dados)


@router.get("/{cadencia_id}", response_model=CadenciaSchema)
def obter_cadencia(
    cadencia_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> CadenciaSchema:
    return cadencia_service.obter(db, tenant_id, cadencia_id)


@router.post("/{cadencia_id}/gerar", response_model=GerarCadenciaResponseSchema)
def gerar_cadencia_para_lote(
    cadencia_id: int,
    dados: GerarCadenciaRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
) -> GerarCadenciaResponseSchema:
    resultado = cadencia_service.gerar_para_lote(db, tenant_id, ator_id, cadencia_id, dados.conta_ids, llm)
    return GerarCadenciaResponseSchema(**resultado)


@router.post("/{cadencia_id}/ativar", response_model=AtivarCadenciaResponseSchema)
def ativar_cadencia(
    cadencia_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
    plan_limits: PlanLimitsProvider = Depends(get_plan_limits_provider),
) -> AtivarCadenciaResponseSchema:
    resultado = cadencia_service.ativar(db, tenant_id, ator_id, cadencia_id, plan_limits)
    return AtivarCadenciaResponseSchema(**resultado)


@router.get("/{cadencia_id}/teste-ab", response_model=RelatorioAbTesteSchema)
def relatorio_teste_ab(
    cadencia_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> RelatorioAbTesteSchema:
    """Relatório de vencedora do teste A/B por taxa de resposta (E3-H5)."""
    return RelatorioAbTesteSchema(**ab_teste_service.relatorio(db, tenant_id, cadencia_id))
