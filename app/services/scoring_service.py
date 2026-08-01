from sqlalchemy.orm import Session

from app.models.conversa_qualificacao import ConversaQualificacao
from app.models.qualificacao import QualificacaoScore

# Etapas do roteiro S.H.A.R.K. de qualificação, na ordem do critério de
# aceite do E5-H1 (dores, contexto, orçamento, autoridade, timing).
ETAPAS = ["dores", "contexto", "orcamento", "autoridade", "timing"]
_PONTOS_POR_ETAPA = 100 / len(ETAPAS)


def etapas_concluidas_ate(etapa_atual: str) -> set[str]:
    if etapa_atual == "concluida":
        return set(ETAPAS)
    if etapa_atual not in ETAPAS:
        return set()
    indice = ETAPAS.index(etapa_atual)
    return set(ETAPAS[:indice])


def calcular(etapas_concluidas: set[str]) -> dict:
    """Score S.H.A.R.K. objetivo com decomposição por critério (E5-H2).

    Função pura: cada etapa concluída do roteiro vale a mesma fração do
    score total. Testável isoladamente, sem tocar o banco.
    """
    criterios = {etapa: (_PONTOS_POR_ETAPA if etapa in etapas_concluidas else 0.0) for etapa in ETAPAS}
    return {"score_total": round(sum(criterios.values()), 2), "criterios": criterios}


def recalcular_e_salvar(
    db: Session, tenant_id: str, conversa: ConversaQualificacao, limiar: float
) -> QualificacaoScore:
    """Score recalculado a cada nova interação relevante (E5-H2)."""
    resultado = calcular(etapas_concluidas_ate(conversa.etapa_atual))
    registro = QualificacaoScore(
        tenant_id=tenant_id,
        conta_id=conversa.conta_id,
        decisor_id=conversa.decisor_id,
        conversa_id=conversa.id,
        score_total=resultado["score_total"],
        criterios=resultado["criterios"],
        limiar_configurado=limiar,
    )
    db.add(registro)
    db.flush()
    return registro
