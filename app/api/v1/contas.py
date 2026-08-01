from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import (
    get_account_data_provider,
    get_ator_id,
    get_db,
    get_graph_client,
    get_llm_provider,
    get_plan_limits_provider,
    get_site_fetcher,
    get_tenant_id,
)
from app.graph.client import Neo4jClient
from app.integrations.site_fetcher import SiteFetcher
from app.llm.base import LLMProvider
from app.providers.account_data.base import AccountDataProvider
from app.providers.plan_limits.base import PlanLimitsProvider
from app.schemas.conta import (
    ContaSchema,
    EnriquecerContaResponseSchema,
    FranquiaSchema,
    GerarListaRequestSchema,
    GerarListaResponseSchema,
    GrafoContaResponseSchema,
)
from app.schemas.decisor import DecisorCreateSchema, DecisorSchema
from app.services import conta_service, franquia_service

router = APIRouter(tags=["contas"])


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
    contas = conta_service.gerar_lista(db, tenant_id, ator_id, icp_id, dados.quantidade, account_data, graph)
    return GerarListaResponseSchema(contas=contas)


@router.get("/contas/franquia", response_model=FranquiaSchema)
def franquia_atual(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
    plan_limits: PlanLimitsProvider = Depends(get_plan_limits_provider),
) -> FranquiaSchema:
    return FranquiaSchema(**franquia_service.obter_franquia(db, tenant_id, plan_limits))


@router.get("/contas/{conta_id}", response_model=ContaSchema)
def obter_conta(
    conta_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> ContaSchema:
    return conta_service.obter(db, tenant_id, conta_id)


@router.post("/contas/{conta_id}/enriquecer", response_model=EnriquecerContaResponseSchema)
def enriquecer_conta(
    conta_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
    llm: LLMProvider = Depends(get_llm_provider),
    site_fetcher: SiteFetcher = Depends(get_site_fetcher),
) -> EnriquecerContaResponseSchema:
    campos = conta_service.enriquecer(db, tenant_id, ator_id, conta_id, llm, site_fetcher)
    return EnriquecerContaResponseSchema(campos=campos)


@router.post("/contas/{conta_id}/decisores/mapear", response_model=list[DecisorSchema])
def mapear_decisores(
    conta_id: int,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
    account_data: AccountDataProvider = Depends(get_account_data_provider),
    graph: Neo4jClient = Depends(get_graph_client),
) -> list[DecisorSchema]:
    return conta_service.mapear_decisores(db, tenant_id, ator_id, conta_id, account_data, graph)


@router.post("/contas/{conta_id}/decisores", response_model=DecisorSchema, status_code=201)
def criar_decisor(
    conta_id: int,
    dados: DecisorCreateSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
    graph: Neo4jClient = Depends(get_graph_client),
) -> DecisorSchema:
    return conta_service.criar_decisor_manual(db, tenant_id, ator_id, conta_id, dados, graph)


@router.get("/contas/{conta_id}/grafo", response_model=GrafoContaResponseSchema)
def grafo_conta(
    conta_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
    graph: Neo4jClient = Depends(get_graph_client),
) -> GrafoContaResponseSchema:
    return GrafoContaResponseSchema(**conta_service.grafo(db, tenant_id, conta_id, graph))


@router.get("/contas/{conta_id}/export/pdf")
def exportar_conta_pdf(
    conta_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> Response:
    conteudo_pdf = conta_service.exportar_pdf(db, tenant_id, conta_id)
    return Response(content=conteudo_pdf, media_type="application/pdf")
