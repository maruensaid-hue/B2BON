"""Contrato público do contexto MAP (Fase 1).

Único ponto por onde código de fora do MAP (CRM, serviços legados,
futuras APIs `/api/v1/map/*`) consome saúde de conta, economia de
cliente e desempenho por vendedor.
"""

from sqlalchemy.orm import Session

from app.contexts.map import economics, interacoes, risk, saude
from app.contexts.map.data_source import CanonicalMapDataSource, CrmInternoMapDataSource, MapDataSource
from app.models.usuario import Usuario

calcular_roi = economics.calcular_roi
listar_interacoes = interacoes.listar_interacoes
TIPOS_INTERACAO_VALIDOS = risk.TIPOS_VALIDOS
calcular_score = risk.calcular_score
classificar = risk.classificar


__all__ = ["CanonicalMapDataSource", "CrmInternoMapDataSource", "MapDataSource"]


def _fonte(db: Session, fonte: MapDataSource | None) -> MapDataSource:
    return fonte or CrmInternoMapDataSource(db)


def score_risco_conta(db: Session, conta: saude.ContaAvaliavel) -> dict:
    return saude.score_risco_conta(db, conta)


def valor_pipeline_aberto(db: Session, tenant_id: str, conta_id: int, fonte: MapDataSource | None = None) -> float:
    return _fonte(db, fonte).valor_pipeline_aberto(tenant_id, conta_id)


def cs_score(db: Session, tenant_id: str, conta_ids: list[int], scores_risco: list[float]) -> dict:
    notas = CrmInternoMapDataSource(db).notas_nps(tenant_id, conta_ids)
    return economics.calcular_cs_score(notas, scores_risco)


def economia(
    db: Session,
    tenant_id: str,
    periodo: str,
    vendedor_usuario_id: int | None = None,
    fonte: MapDataSource | None = None,
) -> dict:
    fonte_efetiva = _fonte(db, fonte)
    return economics.dashboard_economia(
        fonte_efetiva,
        lambda conta: saude.score_risco(fonte_efetiva, conta)["score"],
        tenant_id,
        periodo,
        vendedor_usuario_id,
    )


def funil(db: Session, tenant_id: str, vendedor_usuario_id: int | None = None, fonte: MapDataSource | None = None) -> dict:
    return _fonte(db, fonte).funil(tenant_id, vendedor_usuario_id)


def vendedores_com_contas(db: Session, tenant_id: str, fonte: MapDataSource | None = None) -> list[dict]:
    """Árvore vendedor → contas, com o score de risco de cada conta. Só
    vendedores com ao menos 1 conta atribuída aparecem."""
    fonte_efetiva = _fonte(db, fonte)
    contas = fonte_efetiva.contas(tenant_id, apenas_com_vendedor=True)
    if not contas:
        return []

    ids_vendedores = {conta.vendedor_usuario_id for conta in contas}
    usuarios_por_id = {usuario.id: usuario for usuario in db.query(Usuario).filter(Usuario.id.in_(ids_vendedores)).all()}

    agrupado: dict[int, dict] = {}
    for conta in contas:
        usuario = usuarios_por_id.get(conta.vendedor_usuario_id)
        grupo = agrupado.setdefault(
            conta.vendedor_usuario_id,
            {"usuario_id": conta.vendedor_usuario_id, "nome": usuario.nome if usuario else "Desconhecido", "contas": []},
        )
        risco = saude.score_risco(fonte_efetiva, conta)
        grupo["contas"].append(
            {
                "id": conta.id,
                "nome": conta.nome,
                "nome_fantasia": conta.nome_fantasia,
                "score": risco["score"],
                "classificacao": risco["classificacao"],
            }
        )

    resultado = list(agrupado.values())
    resultado.sort(key=lambda item: item["nome"])
    return resultado
