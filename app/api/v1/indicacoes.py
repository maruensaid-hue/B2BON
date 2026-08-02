from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_db, get_graph_client, get_rede_social_provider, get_tenant_id
from app.graph.client import Neo4jClient
from app.providers.rede_social.base import RedeSocialProvider
from app.schemas.indicacao import ConverterIndicacaoRequestSchema, IndicacaoSchema
from app.services import indicacao_service

router = APIRouter(prefix="/indicacoes", tags=["indicacoes"])


@router.get("", response_model=list[IndicacaoSchema])
def listar_indicacoes(
    status: str | None = None,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
) -> list[IndicacaoSchema]:
    return indicacao_service.listar(db, tenant_id, status)


@router.post("/{codigo}/converter", response_model=IndicacaoSchema)
def converter_indicacao(
    codigo: str,
    dados: ConverterIndicacaoRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
    rede_social: RedeSocialProvider = Depends(get_rede_social_provider),
    graph: Neo4jClient = Depends(get_graph_client),
) -> IndicacaoSchema:
    """Liga a indicação a uma conta real, identifica indicação intra-rede
    e registra a aresta no grafo (E11-H3)."""
    return indicacao_service.converter(db, tenant_id, ator_id, codigo, dados.conta_id, rede_social, graph)
