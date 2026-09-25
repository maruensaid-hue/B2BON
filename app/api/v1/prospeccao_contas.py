"""Rotas de prospecção do PREDATOR sobre contas (Fase 1, acoplamento C3).

Até a Fase 1 estas rotas moravam em `contas.py`, sob o gate do CRM: um
tenant só-PREDATOR não conseguia gerar lista nem enriquecer, e um só-CRM
recebia rotas de prospecção. Os paths são os mesmos de antes (o frontend
não muda); o que muda é o gate (`_exige_predator` em `router.py`). Este
router é incluído ANTES de `contas.py` para `/contas/franquia` e
`/contas/limite-enriquecimento` não caírem em `/contas/{conta_id}`.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import (
    get_account_data_provider,
    get_ator_id,
    get_brasilapi_client,
    get_contact_enrichment_provider,
    get_db,
    get_graph_client,
    get_llm_provider,
    get_plan_limits_provider,
    get_site_fetcher,
    get_tenant_id,
    get_web_search_provider,
    limitar_ia_por_tenant,
)
from app.contexts.predator import contract as prospeccao
from app.graph.client import Neo4jClient
from app.integrations.brasilapi_client import BrasilApiClient
from app.integrations.site_fetcher import SiteFetcher
from app.llm.base import LLMProvider
from app.providers.account_data.base import AccountDataProvider
from app.providers.contact_enrichment.base import ContactEnrichmentProvider
from app.providers.plan_limits.base import PlanLimitsProvider
from app.providers.web_search.base import WebSearchProvider
from app.schemas.conta import (
    EnriquecerContaResponseSchema,
    EnriquecerEmLoteRequestSchema,
    EnriquecerEmLoteResponseSchema,
    FranquiaSchema,
    GerarListaRequestSchema,
    GerarListaResponseSchema,
    LimiteEnriquecimentoResponseSchema,
)
from app.schemas.decisor import DecisorSchema
from app.services import enriquecimento_limite_service, franquia_service

from app.api.v1.contas import _serializar_decisores_com_linkedin

router = APIRouter(tags=["prospeccao"])


@router.post("/icp/{icp_id}/contas/gerar", response_model=GerarListaResponseSchema, status_code=201)
def gerar_lista(
    icp_id: int,
    dados: GerarListaRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
    account_data: AccountDataProvider = Depends(get_account_data_provider),
    graph: Neo4jClient = Depends(get_graph_client),
) -> GerarListaResponseSchema:
    contas = prospeccao.gerar_lista(db, tenant_id, ator_id, icp_id, dados.quantidade, account_data, graph)
    return GerarListaResponseSchema(contas=contas)


@router.get("/contas/franquia", response_model=FranquiaSchema)
def franquia_atual(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
    plan_limits: PlanLimitsProvider = Depends(get_plan_limits_provider),
) -> FranquiaSchema:
    return FranquiaSchema(**franquia_service.obter_franquia(db, tenant_id, plan_limits))


@router.get("/contas/limite-enriquecimento", response_model=LimiteEnriquecimentoResponseSchema)
def limite_enriquecimento_atual(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
    plan_limits: PlanLimitsProvider = Depends(get_plan_limits_provider),
) -> LimiteEnriquecimentoResponseSchema:
    """Limite semanal de pesquisas de enriquecimento — todo plano tem
    limite configurado, proporcional à franquia mensal (raio-X
    2026-08-28); `limite: null` fica reservado pra um plano futuro sem
    teto."""
    return LimiteEnriquecimentoResponseSchema(**enriquecimento_limite_service.obter_limites(db, tenant_id, plan_limits))


@router.post("/contas/enriquecer-em-lote", response_model=EnriquecerEmLoteResponseSchema)
def enriquecer_contas_em_lote(
    dados: EnriquecerEmLoteRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> EnriquecerEmLoteResponseSchema:
    """Enfileira as contas selecionadas pra enriquecimento em lote (site +
    decisores) — processado aos poucos pelo cron a cada 15min, mesma fila
    usada pela importação de planilha de evento. Não roda na hora (cada
    conta passa por LLM + busca web + Lusha), pra não estourar o timeout
    do proxy do Render."""
    return EnriquecerEmLoteResponseSchema(
        **prospeccao.enfileirar_enriquecimento_em_lote(db, tenant_id, dados.conta_ids)
    )


@router.post(
    "/contas/{conta_id}/enriquecer",
    response_model=EnriquecerContaResponseSchema,
    dependencies=[Depends(limitar_ia_por_tenant())],
)
def enriquecer_conta(
    conta_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
    site_fetcher: SiteFetcher = Depends(get_site_fetcher),
    web_search: WebSearchProvider = Depends(get_web_search_provider),
    plan_limits: PlanLimitsProvider = Depends(get_plan_limits_provider),
) -> EnriquecerContaResponseSchema:
    campos = prospeccao.enriquecer(db, tenant_id, ator_id, conta_id, llm, site_fetcher, web_search, plan_limits)
    return EnriquecerContaResponseSchema(campos=campos)


@router.post("/contas/{conta_id}/enriquecer-brasilapi", response_model=EnriquecerContaResponseSchema)
def enriquecer_conta_via_brasilapi(
    conta_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
    brasilapi_client: BrasilApiClient = Depends(get_brasilapi_client),
) -> EnriquecerContaResponseSchema:
    campos = prospeccao.enriquecer_via_brasilapi(db, tenant_id, ator_id, conta_id, brasilapi_client)
    return EnriquecerContaResponseSchema(campos=campos)


@router.post("/contas/{conta_id}/decisores/mapear", response_model=list[DecisorSchema])
def mapear_decisores(
    conta_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
    account_data: AccountDataProvider = Depends(get_account_data_provider),
    contact_enrichment: ContactEnrichmentProvider = Depends(get_contact_enrichment_provider),
    graph: Neo4jClient = Depends(get_graph_client),
    plan_limits: PlanLimitsProvider = Depends(get_plan_limits_provider),
) -> list[DecisorSchema]:
    decisores = prospeccao.mapear_decisores(
        db, tenant_id, ator_id, conta_id, account_data, contact_enrichment, graph, plan_limits
    )
    return _serializar_decisores_com_linkedin(db, tenant_id, conta_id, ator_id, decisores)
