from app.services import central_negocios_service


def setup_function() -> None:
    central_negocios_service.resetar_cache()


def test_obter_mercado_usa_cache_dentro_do_ttl() -> None:
    chamadas = []

    def client():
        chamadas.append(1)
        return {"ibovespa": {"pontos": 1.0, "variacao_pct": 0.1}, "cambio": []}

    central_negocios_service.obter_mercado(client)
    central_negocios_service.obter_mercado(client)

    assert len(chamadas) == 1


def test_obter_mercado_atualiza_apos_resetar_cache() -> None:
    chamadas = []

    def client():
        chamadas.append(1)
        return {"ibovespa": None, "cambio": []}

    central_negocios_service.obter_mercado(client)
    central_negocios_service.resetar_cache()
    central_negocios_service.obter_mercado(client)

    assert len(chamadas) == 2


def test_obter_mercado_propaga_fonte_indisponivel_sem_inventar_dado() -> None:
    resultado = central_negocios_service.obter_mercado(lambda: {"ibovespa": None, "cambio": []})

    assert resultado["ibovespa"] is None
    assert resultado["cambio"] == []


def test_obter_noticias_usa_cache_dentro_do_ttl() -> None:
    chamadas = []

    def client():
        chamadas.append(1)
        return [{"portal": "UOL Economia", "titulo": "Teste", "link": "https://exemplo.com", "publicado_em": None}]

    central_negocios_service.obter_noticias(client)
    central_negocios_service.obter_noticias(client)

    assert len(chamadas) == 1
