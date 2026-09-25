"""PREDATOR API — `/api/v1/predator/*` (Fase 3, Master Prompt §66).

Nesta fase: leitura de ICPs e contas (canônico), enriquecimento de
empresa por CNPJ (fonte oficial BrasilAPI, sem persistir) e geração de
lista por ICP (escrita, exige `Idempotency-Key`). Geração de mensagem,
cadência e resposta assistida (IA) entram na Fase 4, pelo gateway medido.
"""

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy.orm import Session

from app.api.deps import (
    ContextoApi,
    autenticar_api,
    get_account_data_provider,
    get_brasilapi_client,
    get_db,
    get_graph_client,
)
from app.api.v1.produto.schemas import EnriquecerEmpresaRequest, GerarListaApiRequest
from app.contexts.integrations import contract as integracoes
from app.contexts.platform.contract import idempotencia
from app.contexts.predator import contract as predator
from app.contexts.shared.canonical.base import DataOrigin
from app.graph.client import Neo4jClient
from app.integrations.brasilapi_client import BrasilApiClient
from app.models.icp import ICP
from app.providers.account_data.base import AccountDataProvider
from app.services.errors import ValidacaoFalhou

router = APIRouter(prefix="/predator", tags=["api-predator"])

_leitura = autenticar_api("predator:read", "predator")
_escrita = autenticar_api("predator:write", "predator")


@router.get("/icps")
def listar_icps(ctx: ContextoApi = Depends(_leitura), db: Session = Depends(get_db)) -> list[dict]:
    icps = db.query(ICP).filter_by(tenant_id=ctx.tenant_id).order_by(ICP.id).all()
    return [{"id": i.id, "nome": i.nome, "segmento": i.segmento, "porte": i.porte, "regiao": i.regiao} for i in icps]


@router.get("/accounts")
def listar_contas(
    cursor: str | None = None, limit: int = 100, ctx: ContextoApi = Depends(_leitura), db: Session = Depends(get_db)
) -> dict:
    if not 1 <= limit <= 500:
        raise ValidacaoFalhou("limit deve estar entre 1 e 500.")
    if cursor is not None and not cursor.isdigit():
        raise ValidacaoFalhou("cursor inválido.")
    pagina = integracoes.adapter_b2bon(db).list_accounts(ctx.tenant_id, cursor=cursor, limit=limit)
    return pagina.model_dump(mode="json")


@router.post("/company/enrich")
def enriquecer_empresa(
    dados: EnriquecerEmpresaRequest,
    ctx: ContextoApi = Depends(_leitura),
    brasilapi: BrasilApiClient = Depends(get_brasilapi_client),
) -> dict:
    cnpj = "".join(ch for ch in dados.cnpj if ch.isdigit())
    if len(cnpj) != 14:
        raise ValidacaoFalhou("CNPJ deve ter 14 dígitos.")
    return {"cnpj": cnpj, "origin": DataOrigin.OFFICIAL, "source": {"system": "brasilapi", "entity": "cnpj", "external_id": cnpj}, "dados": brasilapi(cnpj)}


@router.post("/lists/generate", status_code=201)
def gerar_lista(
    dados: GerarListaApiRequest,
    response: Response,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    ctx: ContextoApi = Depends(_escrita),
    db: Session = Depends(get_db),
    account_data: AccountDataProvider = Depends(get_account_data_provider),
    graph: Neo4jClient = Depends(get_graph_client),
) -> dict:
    chave = idempotencia.validar_chave(idempotency_key)
    rota = "POST /predator/lists/generate"
    corpo = dados.model_dump()
    anterior = idempotencia.buscar(db, ctx.tenant_id, chave, rota, corpo)
    if anterior is not None:
        response.status_code = anterior.status_code
        response.headers["Idempotent-Replayed"] = "true"
        return anterior.resposta
    contas = predator.gerar_lista(db, ctx.tenant_id, f"api-key:{ctx.chave_id}", dados.icp_id, dados.quantidade, account_data, graph)
    resposta = {"contas": [{"id": c.id, "nome": c.nome, "cnpj": c.cnpj, "score_aderencia": c.score_aderencia} for c in contas]}
    idempotencia.gravar(db, ctx.tenant_id, chave, rota, corpo, 201, resposta)
    return resposta
