"""Histórico das coletas de site: lista, detalhe (fontes, domínio, indicadores), confirmação manual do domínio e reprocessamento."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import (
    get_ator_id,
    get_brasilapi_client,
    get_db,
    get_llm_provider,
    get_plan_limits_provider,
    get_site_fetcher,
    get_tenant_id,
    get_web_search_provider,
    limitar_ia_por_tenant,
)
from app.contexts.predator import contract as prospeccao
from app.integrations.brasilapi_client import BrasilApiClient
from app.integrations.site_fetcher import SiteFetcher
from app.llm.base import LLMProvider
from app.providers.plan_limits.base import PlanLimitsProvider
from app.providers.web_search.base import WebSearchProvider
from app.services import coleta_site_service
from app.services.errors import RegraNegocioViolada

router = APIRouter(prefix="/coletas-site", tags=["coletas-site"])


@router.get("")
def listar_coletas(conta_id: int | None = None, estado: str | None = None, limite: int = 50,
                   tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> list[dict]:
    return coleta_site_service.listar(db, tenant_id, conta_id, estado, limite)


@router.get("/{coleta_id}")
def detalhe_coleta(coleta_id: int, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> dict:
    return coleta_site_service.detalhe(db, tenant_id, coleta_id)


@router.post("/{coleta_id}/confirmar-dominio")
def confirmar_dominio(coleta_id: int, tenant_id: str = Depends(get_tenant_id), ator_id: str | None = Depends(get_ator_id),
                      db: Session = Depends(get_db)) -> dict:
    coleta_site_service.confirmar_dominio(db, tenant_id, ator_id, coleta_id)
    return coleta_site_service.detalhe(db, tenant_id, coleta_id)


@router.post("/{coleta_id}/reprocessar", dependencies=[Depends(limitar_ia_por_tenant())])
def reprocessar(
    coleta_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
    site_fetcher: SiteFetcher = Depends(get_site_fetcher),
    web_search: WebSearchProvider = Depends(get_web_search_provider),
    plan_limits: PlanLimitsProvider = Depends(get_plan_limits_provider),
    brasilapi_client: BrasilApiClient = Depends(get_brasilapi_client),
) -> dict:
    """Nova coleta da mesma conta (com o domínio atual dela). Não apaga nem altera a coleta original: gera um novo registro
    ligado a ela. Uma coleta ainda em andamento não é reprocessada."""
    original = coleta_site_service.obter(db, tenant_id, coleta_id)
    if original.estado == "em_andamento":
        raise RegraNegocioViolada("Esta coleta ainda está em andamento.")
    prospeccao.enriquecer(
        db, tenant_id, ator_id, original.conta_id, llm, site_fetcher, web_search, plan_limits,
        consulta_cnpj=brasilapi_client, disparo="reprocesso", reprocesso_de_id=original.id,
    )
    nova = coleta_site_service.listar(db, tenant_id, conta_id=original.conta_id, limite=1)[0]
    return coleta_site_service.detalhe(db, tenant_id, nova["id"])
