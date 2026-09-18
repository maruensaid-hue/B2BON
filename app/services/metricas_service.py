"""ROI e CS (Customer Success) — métricas que existiam numa versão
anterior do MAP, antes de integrar à B2B ON (pedido do usuário: trazer
de volta pro Dashboard e pro MAP). Módulo dedicado porque tanto
`crm_service` (Dashboard) quanto `saude_conta_service` (MAP) precisam
das duas, e uma importar da outra criaria dependência circular."""

from collections import Counter

from sqlalchemy.orm import Session

from app.models.decisor import Decisor
from app.models.estagio_funil import EstagioFunil
from app.models.negocio import Negocio
from app.models.pesquisa_nps import PesquisaNps

_AMOSTRA_MINIMA_PADRAO = 3


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


def calcular_padroes_observados(db: Session, tenant_id: str) -> dict:
    """Company Learning (master prompt §12, §15, Fase 0.5-B) — só
    correlação OBSERVADA com amostra explícita, nunca causal (§15 é
    literal: "observed_pattern, correlation, confidence, sample_size").
    Nenhum dado inventado (§21): tudo calculado a partir de `Negocio`/
    `Decisor` já persistidos por outras fases (Fase 5B Stakeholder Map,
    CRM Core) — abaixo de `_AMOSTRA_MINIMA_PADRAO`, o campo vem `None`
    em vez de reportar um número que não significa nada com tão pouco
    dado."""
    negocios_ganhos = (
        db.query(Negocio)
        .join(EstagioFunil, EstagioFunil.id == Negocio.estagio_id)
        .filter(Negocio.tenant_id == tenant_id, EstagioFunil.tipo == "ganho")
        .all()
    )
    negocios_perdidos = (
        db.query(Negocio)
        .join(EstagioFunil, EstagioFunil.id == Negocio.estagio_id)
        .filter(Negocio.tenant_id == tenant_id, EstagioFunil.tipo == "perdido")
        .all()
    )

    amostra_ticket = len(negocios_ganhos)
    ticket_medio = (
        sum(negocio.valor for negocio in negocios_ganhos) / amostra_ticket
        if amostra_ticket >= _AMOSTRA_MINIMA_PADRAO
        else None
    )

    ciclos_dias = [
        (negocio.ganho_em - negocio.criado_em).days for negocio in negocios_ganhos if negocio.ganho_em is not None
    ]
    amostra_ciclo = len(ciclos_dias)
    ciclo_medio_dias = sum(ciclos_dias) / amostra_ciclo if amostra_ciclo >= _AMOSTRA_MINIMA_PADRAO else None

    motivos_perda = [negocio.motivo_perda for negocio in negocios_perdidos if negocio.motivo_perda]
    amostra_motivo_perda = len(motivos_perda)
    motivo_perda_mais_comum = None
    motivo_perda_mais_comum_contagem = 0
    if motivos_perda:
        motivo_perda_mais_comum, motivo_perda_mais_comum_contagem = Counter(motivos_perda).most_common(1)[0]

    def _tem_decision_maker_confirmado(conta_id: int) -> bool:
        return (
            db.query(Decisor)
            .filter_by(tenant_id=tenant_id, conta_id=conta_id, papel_confirmado="DECISION_MAKER")
            .first()
            is not None
        )

    negocios_fechados = negocios_ganhos + negocios_perdidos
    amostra_decision_maker = len(negocios_fechados)
    taxa_ganho_com_decision_maker = None
    taxa_ganho_sem_decision_maker = None
    if amostra_decision_maker >= _AMOSTRA_MINIMA_PADRAO:
        com_dm = [negocio for negocio in negocios_fechados if _tem_decision_maker_confirmado(negocio.conta_id)]
        sem_dm = [negocio for negocio in negocios_fechados if not _tem_decision_maker_confirmado(negocio.conta_id)]
        if com_dm:
            taxa_ganho_com_decision_maker = len([negocio for negocio in com_dm if negocio in negocios_ganhos]) / len(com_dm)
        if sem_dm:
            taxa_ganho_sem_decision_maker = len([negocio for negocio in sem_dm if negocio in negocios_ganhos]) / len(sem_dm)

    return {
        "ticket_medio": ticket_medio,
        "amostra_ticket_medio": amostra_ticket,
        "ciclo_medio_dias": ciclo_medio_dias,
        "amostra_ciclo_medio": amostra_ciclo,
        "motivo_perda_mais_comum": motivo_perda_mais_comum,
        "motivo_perda_mais_comum_contagem": motivo_perda_mais_comum_contagem,
        "amostra_motivo_perda": amostra_motivo_perda,
        "taxa_ganho_com_decision_maker": taxa_ganho_com_decision_maker,
        "taxa_ganho_sem_decision_maker": taxa_ganho_sem_decision_maker,
        "amostra_decision_maker": amostra_decision_maker,
    }
