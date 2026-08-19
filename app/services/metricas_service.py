"""ROI e CS (Customer Success) — métricas que existiam numa versão
anterior do MAP, antes de integrar à B2B ON (pedido do usuário: trazer
de volta pro Dashboard e pro MAP). Módulo dedicado porque tanto
`crm_service` (Dashboard) quanto `saude_conta_service` (MAP) precisam
das duas, e uma importar da outra criaria dependência circular."""

from sqlalchemy.orm import Session

from app.models.pesquisa_nps import PesquisaNps


def calcular_roi(ltv_medio: float | None, cac: float | None) -> float | None:
    """Razão LTV/CAC — quanto retorno cada real gasto pra adquirir um
    cliente trouxe de volta ao longo do relacionamento. Sem os dois
    valores (ex.: nenhum cliente novo no período, sem custo de aquisição
    lançado), não há como calcular."""
    if not ltv_medio or not cac:
        return None
    return ltv_medio / cac


def calcular_cs_score(db: Session, tenant_id: str, conta_ids: list[int], scores_risco: list[float]) -> dict:
    """Mistura NPS médio (satisfação declarada pelo cliente) com o
    inverso do score de risco de churn já calculado em
    `saude_conta_service`/`motor_service` (saúde da relação, sem duplicar
    essa lógica aqui — os scores já vêm prontos de quem chamou). Com só
    um dos dois disponível, usa o que tiver; sem nenhum, `cs_score` fica
    `None` em vez de fingir um número."""
    notas = (
        [
            nota
            for (nota,) in db.query(PesquisaNps.nota)
            .filter(
                PesquisaNps.tenant_id == tenant_id,
                PesquisaNps.conta_id.in_(conta_ids),
                PesquisaNps.nota.isnot(None),
            )
            .all()
        ]
        if conta_ids
        else []
    )
    nps_medio = (sum(notas) / len(notas)) if notas else None

    saudes = [100.0 - score for score in scores_risco]
    saude_media = (sum(saudes) / len(saudes)) if saudes else None

    # nps_medio é 0-10 (padrão NPS) — normaliza pra 0-100 antes de misturar
    # com saude_media, que já está em 0-100.
    componentes = [v for v in ((nps_medio * 10) if nps_medio is not None else None, saude_media) if v is not None]
    cs_score = (sum(componentes) / len(componentes)) if componentes else None

    return {"cs_score": cs_score, "nps_medio": nps_medio, "saude_media": saude_media}
