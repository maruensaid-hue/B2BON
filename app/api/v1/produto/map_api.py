"""MAP API — `/api/v1/map/*` (Fase 3, Master Prompt §65).

Consumível por qualquer CRM: sem `dados`, calcula sobre o CRM da B2B ON
do tenant; com `dados` (modelo canônico), calcula sobre o que o cliente
enviou, sem persistir nada. Autenticação por chave de API com escopo
`map:read` e módulo MAP contratado.

`/map/churn/remediation` (texto gerado por IA) entra na Fase 4, quando
toda chamada de IA passa pelo gateway medido.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import ContextoApi, autenticar_api, get_db
from app.api.v1.produto.schemas import (
    ChurnResponse,
    CustomerScoreItem,
    CustomerScoreResponse,
    DadosCanonicosMap,
    MapAnaliseResponse,
    MapContasRequest,
    MapRequest,
    MetricaResponse,
    RiscoConta,
)
from app.contexts.integrations import contract as integracoes
from app.contexts.map import contract as map_contract

router = APIRouter(prefix="/map", tags=["api-map"])

_auth = autenticar_api("map:read", "map")


def _fonte(db: Session, tenant_id: str, dados: DadosCanonicosMap | None):
    if dados is None:
        return "b2bon_crm", map_contract.CrmInternoMapDataSource(db)
    adapter = integracoes.adapter_de_payload(
        tenant_id,
        organizations=dados.organizations, accounts=dados.accounts, customers=dados.customers,
        opportunities=dados.opportunities, stages=dados.stages, interactions=dados.interactions,
        cs_metrics=dados.cs_metrics,
    )
    custo = dados.custo_aquisicao_periodo
    return "api_payload", map_contract.CanonicalMapDataSource(adapter, custo_aquisicao=lambda _t, _p: custo)


def _riscos(fonte, tenant_id: str, conta_ids: list[str] | None) -> list[RiscoConta]:
    contas = fonte.contas(tenant_id)
    if conta_ids is not None:
        filtro = set(conta_ids)
        contas = [c for c in contas if str(c.id) in filtro]
    resultado = []
    for conta in contas:
        risco = map_contract.score_risco(fonte, conta)
        resultado.append(
            RiscoConta(
                conta_id=str(conta.id), nome=conta.nome_fantasia or conta.nome, score=risco["score"],
                classificacao=risco["classificacao"], dias_sem_contato=risco["dias_sem_contato"], sinais=risco["sinais"],
            )
        )
    return sorted(resultado, key=lambda r: r.score, reverse=True)


@router.post("/analyze", response_model=MapAnaliseResponse)
def analisar(dados: MapRequest, ctx: ContextoApi = Depends(_auth), db: Session = Depends(get_db)) -> MapAnaliseResponse:
    nome_fonte, fonte = _fonte(db, ctx.tenant_id, dados.dados)
    economia = map_contract.economia(db, ctx.tenant_id, dados.periodo, fonte=fonte)
    return MapAnaliseResponse(fonte=nome_fonte, periodo=dados.periodo, economia=economia, contas=_riscos(fonte, ctx.tenant_id, None))


@router.post("/churn/predict", response_model=ChurnResponse)
def prever_churn(dados: MapContasRequest, ctx: ContextoApi = Depends(_auth), db: Session = Depends(get_db)) -> ChurnResponse:
    nome_fonte, fonte = _fonte(db, ctx.tenant_id, dados.dados)
    return ChurnResponse(fonte=nome_fonte, previsoes=_riscos(fonte, ctx.tenant_id, dados.conta_ids))


@router.post("/customer-score", response_model=CustomerScoreResponse)
def customer_score(dados: MapContasRequest, ctx: ContextoApi = Depends(_auth), db: Session = Depends(get_db)) -> CustomerScoreResponse:
    nome_fonte, fonte = _fonte(db, ctx.tenant_id, dados.dados)
    itens = []
    for risco in _riscos(fonte, ctx.tenant_id, dados.conta_ids):
        conta_id = risco.conta_id if nome_fonte == "api_payload" else int(risco.conta_id)
        cs = map_contract.calcular_cs_score(fonte.notas_nps(ctx.tenant_id, [conta_id]), [risco.score])
        itens.append(CustomerScoreItem(conta_id=risco.conta_id, cs_score=cs["cs_score"], nps_medio=cs["nps_medio"], saude=100.0 - risco.score))
    return CustomerScoreResponse(fonte=nome_fonte, contas=itens)


def _metrica(nome: str, chaves: list[str]):
    def _endpoint(dados: MapRequest, ctx: ContextoApi = Depends(_auth), db: Session = Depends(get_db)) -> MetricaResponse:
        nome_fonte, fonte = _fonte(db, ctx.tenant_id, dados.dados)
        economia = map_contract.economia(db, ctx.tenant_id, dados.periodo, fonte=fonte)
        return MetricaResponse(fonte=nome_fonte, periodo=dados.periodo, valor=economia[chaves[0]], detalhe={c: economia[c] for c in chaves})

    _endpoint.__name__ = f"metrica_{nome}"
    return _endpoint


router.add_api_route("/ltv", _metrica("ltv", ["ltv_medio", "clientes_ativos_inicio_periodo"]), methods=["POST"], response_model=MetricaResponse)
router.add_api_route("/cac", _metrica("cac", ["cac", "novos_clientes"]), methods=["POST"], response_model=MetricaResponse)
router.add_api_route("/roi", _metrica("roi", ["roi", "ltv_medio", "cac"]), methods=["POST"], response_model=MetricaResponse)
