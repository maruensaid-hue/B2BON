from app.services import scoring_service


def test_score_decomposto_por_criterio():
    """E5-H2: score numérico com decomposição por critério (transparência total)."""
    resultado = scoring_service.calcular({"dores", "contexto"})

    assert resultado["score_total"] == 40.0
    assert resultado["criterios"]["dores"] == 20.0
    assert resultado["criterios"]["contexto"] == 20.0
    assert resultado["criterios"]["orcamento"] == 0.0


def test_score_zero_sem_etapas_concluidas():
    resultado = scoring_service.calcular(set())
    assert resultado["score_total"] == 0.0


def test_score_cheio_com_todas_etapas():
    resultado = scoring_service.calcular(set(scoring_service.ETAPAS))
    assert resultado["score_total"] == 100.0


def test_etapas_concluidas_ate_reflete_ordem_do_roteiro():
    assert scoring_service.etapas_concluidas_ate("dores") == set()
    assert scoring_service.etapas_concluidas_ate("timing") == {"dores", "contexto", "orcamento", "autoridade"}
    assert scoring_service.etapas_concluidas_ate("concluida") == set(scoring_service.ETAPAS)
