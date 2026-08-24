from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_ator_id, get_db, get_graph_client, get_tenant_id
from app.graph.client import Neo4jClient
from app.schemas.conta import ContaSchema, ImportarParticipantesRequestSchema, ImportarParticipantesResponseSchema
from app.schemas.lista_prospeccao import (
    ElegibilidadeContaSchema,
    ExcluirContasRequestSchema,
    ExcluirContasResponseSchema,
    ListaProspeccaoCreateSchema,
    ListaProspeccaoSchema,
)
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


@router.get("/{lista_id}/contas/elegibilidade-exclusao", response_model=list[ElegibilidadeContaSchema])
def elegibilidade_exclusao_lista(
    lista_id: int, tenant_id: str = Depends(get_tenant_id), db: Session = Depends(get_db)
) -> list[ElegibilidadeContaSchema]:
    """Pré-visualização antes de excluir em lote: pra cada conta da lista,
    diz se ela pode ser apagada ou não (e por quê), sem apagar nada."""
    lista_prospeccao_service.obter(db, tenant_id, lista_id)  # 404 se não existir/não for do tenant
    contas = conta_service.listar_por_lista(db, tenant_id, lista_id)
    return conta_service.mapear_elegibilidade_exclusao(db, contas)


@router.delete("/{lista_id}/contas", response_model=ExcluirContasResponseSchema)
def excluir_contas_da_lista(
    lista_id: int,
    dados: ExcluirContasRequestSchema | None = Body(default=None),
    tenant_id: str = Depends(get_tenant_id),
    ator_id: str | None = Depends(get_ator_id),
    db: Session = Depends(get_db),
) -> ExcluirContasResponseSchema:
    """Apaga em lote as contas desta lista que ainda não têm nenhum sinal
    de trabalho real — pra corrigir uma importação malfeita e poder
    reimportar do zero com cargo-alvo/mapeamento de coluna. Conta com
    negócio/mensagem/reunião etc. já registrado não é apagada; volta na
    resposta em `detalhes_bloqueadas`, o lote inteiro não é abortado por
    causa de uma conta bloqueada. `conta_ids` (opcional) restringe à
    seleção feita no frontend a partir da pré-visualização de
    elegibilidade."""
    lista_prospeccao_service.obter(db, tenant_id, lista_id)  # 404 se não existir/não for do tenant
    conta_ids = dados.conta_ids if dados is not None else None
    resultado = conta_service.excluir_lote_por_lista(db, tenant_id, ator_id, lista_id, conta_ids)
    return ExcluirContasResponseSchema(**resultado)
