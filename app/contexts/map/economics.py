"""Economia de cliente do MAP: LTV, CAC, churn, ROI e CS Score.

Movido de `crm_service.dashboard_economia` e `metricas_service` na Fase 1
(C2/TD-002): são métricas do MAP que viviam no código do CRM. O CRM
continua exibindo LTV/CAC no Dashboard dele, mas agora consome daqui via
`app.contexts.map.contract`. Mesma regra de antes: sem dado suficiente,
o valor é `None`, nunca um número inventado.
"""

from collections.abc import Callable
from datetime import date, timedelta

from app.contexts.map.data_source import MapDataSource
from app.contexts.shared.organizations import OrganizationRef


def calcular_roi(ltv_medio: float | None, cac: float | None) -> float | None:
    """Razão LTV/CAC. Sem os dois valores não há como calcular."""
    if not ltv_medio or not cac:
        return None
    return ltv_medio / cac


def calcular_cs_score(notas_nps: list[int], scores_risco: list[float]) -> dict:
    """Mistura NPS médio (0–10, normalizado para 0–100) com o inverso do
    score de risco de churn. Com só um dos dois, usa o que tiver; sem
    nenhum, `cs_score` fica `None`."""
    nps_medio = (sum(notas_nps) / len(notas_nps)) if notas_nps else None

    saudes = [100.0 - score for score in scores_risco]
    saude_media = (sum(saudes) / len(saudes)) if saudes else None

    componentes = [v for v in ((nps_medio * 10) if nps_medio is not None else None, saude_media) if v is not None]
    cs_score = (sum(componentes) / len(componentes)) if componentes else None

    return {"cs_score": cs_score, "nps_medio": nps_medio, "saude_media": saude_media}


def _limites_periodo(periodo: str) -> tuple[date, date]:
    ano, mes = (int(parte) for parte in periodo.split("-"))
    inicio = date(ano, mes, 1)
    proximo_mes = date(ano + 1, 1, 1) if mes == 12 else date(ano, mes + 1, 1)
    return inicio, proximo_mes - timedelta(days=1)


def dashboard_economia(
    fonte: MapDataSource,
    score_risco: Callable[[OrganizationRef], float],
    tenant_id: str,
    periodo: str,
    vendedor_usuario_id: int | None = None,
) -> dict:
    """LTV médio, CAC e taxa de churn do período "YYYY-MM".

    `vendedor_usuario_id` filtra as contas por posse. **`cac`/`roi` são
    sempre `None` quando escopados por vendedor**: o custo de aquisição
    é um número do tenant inteiro, e dividi-lo pelos novos clientes de
    um vendedor produziria um CAC fabricado."""
    inicio_periodo, fim_periodo = _limites_periodo(periodo)

    contas = fonte.contas(tenant_id, vendedor_usuario_id)
    contas_clientes = [conta for conta in contas if conta.cliente_desde is not None]

    valor_ganho_por_conta = fonte.valor_ganho_por_conta(tenant_id, [conta.id for conta in contas])
    ltv_medio = (sum(valor_ganho_por_conta.values()) / len(contas_clientes)) if contas_clientes else None

    novos_clientes = [conta for conta in contas_clientes if inicio_periodo <= conta.cliente_desde.date() <= fim_periodo]

    cac = None
    if vendedor_usuario_id is None:
        custo = fonte.custo_aquisicao(tenant_id, periodo)
        cac = (custo / len(novos_clientes)) if custo is not None and novos_clientes else None

    ativos_inicio = [
        conta
        for conta in contas_clientes
        if conta.cliente_desde.date() < inicio_periodo
        and (conta.cliente_cancelado_em is None or conta.cliente_cancelado_em.date() >= inicio_periodo)
    ]
    cancelados_periodo = [
        conta
        for conta in contas_clientes
        if conta.cliente_cancelado_em and inicio_periodo <= conta.cliente_cancelado_em.date() <= fim_periodo
    ]
    taxa_churn = (len(cancelados_periodo) / len(ativos_inicio)) if ativos_inicio else None

    roi = calcular_roi(ltv_medio, cac) if vendedor_usuario_id is None else None
    cs = calcular_cs_score(
        fonte.notas_nps(tenant_id, [conta.id for conta in contas]),
        [score_risco(conta) for conta in contas],
    )

    return {
        "periodo": periodo,
        "ltv_medio": ltv_medio,
        "cac": cac,
        "taxa_churn": taxa_churn,
        "novos_clientes": len(novos_clientes),
        "clientes_ativos_inicio_periodo": len(ativos_inicio),
        "clientes_cancelados_periodo": len(cancelados_periodo),
        "roi": roi,
        "cs_score": cs["cs_score"],
        "nps_medio": cs["nps_medio"],
    }
