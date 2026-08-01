import math

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.decisor import Decisor
from app.models.mensagem import Mensagem


def _estatisticas_variante(db: Session, tenant_id: str, cadencia_id: int, variante: str) -> tuple[int, int]:
    decisor_ids = {
        decisor_id
        for (decisor_id,) in db.query(Mensagem.decisor_id)
        .filter_by(tenant_id=tenant_id, cadencia_id=cadencia_id, variante_ab=variante, status="enviado")
        .distinct()
        .all()
    }
    if not decisor_ids:
        return 0, 0

    respondentes = (
        db.query(Decisor)
        .filter(Decisor.id.in_(decisor_ids), Decisor.ultima_interacao_em.isnot(None))
        .count()
    )
    return len(decisor_ids), respondentes


def _z_proporcoes(sucesso_a: int, total_a: int, sucesso_b: int, total_b: int) -> float:
    """Teste-Z de duas proporções (aproximação normal, erro padrão pooled)."""
    if total_a == 0 or total_b == 0:
        return 0.0
    p_a = sucesso_a / total_a
    p_b = sucesso_b / total_b
    p_pool = (sucesso_a + sucesso_b) / (total_a + total_b)
    erro_padrao = math.sqrt(p_pool * (1 - p_pool) * (1 / total_a + 1 / total_b))
    if erro_padrao == 0:
        return 0.0
    return (p_a - p_b) / erro_padrao


def relatorio(db: Session, tenant_id: str, cadencia_id: int) -> dict:
    """Relatório de vencedora do teste A/B por taxa de resposta, com
    significância mínima definida por `settings.ab_teste_confianca_z`
    (E3-H5)."""
    total_a, respondentes_a = _estatisticas_variante(db, tenant_id, cadencia_id, "A")
    total_b, respondentes_b = _estatisticas_variante(db, tenant_id, cadencia_id, "B")

    z_score = _z_proporcoes(respondentes_a, total_a, respondentes_b, total_b)
    significativo = abs(z_score) >= settings.ab_teste_confianca_z

    taxa_a = respondentes_a / total_a if total_a else 0.0
    taxa_b = respondentes_b / total_b if total_b else 0.0

    vencedora = None
    if significativo:
        vencedora = "A" if taxa_a > taxa_b else "B"

    return {
        "variante_a": {"total": total_a, "respondentes": respondentes_a, "taxa_resposta": taxa_a},
        "variante_b": {"total": total_b, "respondentes": respondentes_b, "taxa_resposta": taxa_b},
        "z_score": z_score,
        "significativo": significativo,
        "vencedora": vencedora,
    }
