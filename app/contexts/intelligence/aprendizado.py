"""Learning Loop (Fase 4, Master Prompt §18).

    AI RECOMMENDATION → HUMAN REVIEW → EDIT → APPROVAL → EXECUTION → OUTCOME
    → LEARNING EVENT → CORPORATE BRAIN

Registra cada decisão humana sobre conteúdo gerado por IA como evidência
(`evento_aprendizado`) e publica o evento de domínio correspondente
(AIRecommendationAccepted/Rejected). O que vira conhecimento no Corporate
Brain é decisão humana (regra aprendida / item do brain), nunca
automática — correlação não é causalidade.
"""

from sqlalchemy.orm import Session

from app.contexts.shared import events
from app.models.evento_aprendizado import EventoAprendizado

TIPOS = frozenset({"GERADO", "APROVADO", "EDITADO", "REJEITADO", "RESULTADO"})
_EVENTO_DOMINIO = {
    "GERADO": events.TipoEvento.AI_RECOMMENDATION_CREATED,
    "APROVADO": events.TipoEvento.AI_RECOMMENDATION_ACCEPTED,
    "EDITADO": events.TipoEvento.AI_RECOMMENDATION_ACCEPTED,
    "REJEITADO": events.TipoEvento.AI_RECOMMENDATION_REJECTED,
}


def registrar(
    db: Session,
    tenant_id: str,
    feature: str,
    tipo: str,
    *,
    entidade_tipo: str | None = None,
    entidade_id: int | None = None,
    usuario_id: int | str | None = None,
    dados: dict | None = None,
) -> EventoAprendizado:
    """Adiciona na sessão do chamador (flush, sem commit): o evento de
    aprendizado vive e morre com a decisão que o originou."""
    if tipo not in TIPOS:
        raise ValueError(f"Tipo de evento de aprendizado inválido: {tipo}")
    try:
        usuario = int(usuario_id) if usuario_id is not None else None
    except (TypeError, ValueError):
        usuario = None
    evento = EventoAprendizado(
        tenant_id=tenant_id, feature=feature, tipo=tipo, entidade_tipo=entidade_tipo,
        entidade_id=entidade_id, usuario_id=usuario, dados=dados or {},
    )
    db.add(evento)
    db.flush()
    tipo_dominio = _EVENTO_DOMINIO.get(tipo)
    if tipo_dominio is not None:
        events.publicar(
            db, tipo_dominio, tenant_id, entidade_tipo or "recomendacao_ia", entidade_id or evento.id,
            {"feature": feature, "tipo": tipo}, ator_id=str(usuario_id) if usuario_id is not None else None,
        )
    return evento


def resumo(db: Session, tenant_id: str) -> dict:
    linhas = db.query(EventoAprendizado.feature, EventoAprendizado.tipo).filter(EventoAprendizado.tenant_id == tenant_id).all()
    resultado: dict[str, dict[str, int]] = {}
    for feature, tipo in linhas:
        resultado.setdefault(feature, {}).setdefault(tipo, 0)
        resultado[feature][tipo] += 1
    return resultado
