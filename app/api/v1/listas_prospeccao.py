from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_db, get_graph_client, get_tenant_id
from app.graph.client import Neo4jClient
from app.schemas.conta import ContaSchema, ImportarParticipantesRequestSchema, ImportarParticipantesResponseSchema
from app.schemas.lista_prospeccao import ListaProspeccaoCreateSchema, ListaProspeccaoSchema
from app.services import conta_service, lista_prospeccao_service

router = APIRouter(prefix="/listas-prospeccao", tags=["listas-prospeccao"])


@router.post("", response_model=ListaProspeccaoSchema, status_code=201)
def criar_lista(
    dados: ListaProspeccaoCreateSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ListaProspeccaoSchema:
    return lista_prospeccao_service.criar(db, tenant_id, ator_id, dados.nome, dados.icp_id, dados.cargos_alvo)


@router.get("", response_model=list[ListaProspeccaoSchema])
def listar_listas(tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)) -> list[ListaProspeccaoSchema]:
    return lista_prospeccao_service.listar(db, tenant_id)


@router.get("/{lista_id}/contas", response_model=list[ContaSchema])
def listar_contas_da_lista(
    lista_id: int, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)
) -> list[ContaSchema]:
    lista_prospeccao_service.obter(db, tenant_id, lista_id)  # 404 se não existir/não for do tenant
    return conta_service.listar_por_lista(db, tenant_id, lista_id)


@router.post(
    "/{lista_id}/contas/importar-participantes", response_model=ImportarParticipantesResponseSchema, status_code=201
)
def importar_participantes(
    lista_id: int,
    dados: ImportarParticipantesRequestSchema,
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
    graph: Neo4jClient = Depends(get_graph_client),
) -> ImportarParticipantesResponseSchema:
    resultado = conta_service.importar_participantes(db, tenant_id, ator_id, lista_id, dados.participantes, graph)
    return ImportarParticipantesResponseSchema(**resultado)
