from app.services import central_negocios_service


def setup_function() -> None:
    central_negocios_service.resetar_cache()


def test_obter_mercado_usa_cache_dentro_do_ttl(db_session) -> None:
    chamadas = []

    def client():
        chamadas.append(1)
        return {"indices": [{"nome": "Ibovespa", "pontos": 1.0, "variacao_pct": 0.1, "serie": []}], "cambio": []}

    central_negocios_service.obter_mercado(client, db_session)
    central_negocios_service.obter_mercado(client, db_session)

    assert len(chamadas) == 1


def test_obter_mercado_atualiza_apos_resetar_cache(db_session) -> None:
    chamadas = []

    def client():
        chamadas.append(1)
        return {"indices": [], "cambio": []}

    central_negocios_service.obter_mercado(client, db_session)
    central_negocios_service.resetar_cache()
    central_negocios_service.obter_mercado(client, db_session)

    assert len(chamadas) == 2


def test_obter_mercado_propaga_fonte_indisponivel_sem_inventar_dado(db_session) -> None:
    resultado = central_negocios_service.obter_mercado(lambda: {"indices": [], "cambio": []}, db_session)

    assert resultado["indices"] == []
    assert resultado["cambio"] == []


def test_obter_mercado_mantem_dado_antigo_quando_nova_busca_falha(db_session) -> None:
    """Fallback stale-enquanto-revalida (raio-X 2026-09-21, AwesomeAPI
    rate-limitando em produção): uma falha pontual na fonte não pode
    apagar a última cotação boa que já tínhamos."""
    indices_bons = [{"nome": "Ibovespa", "pontos": 100.0, "variacao_pct": 1.0, "serie": []}]
    cambio_bom = [{"codigo": "USD", "nome": "USD", "valor": 5.0, "variacao_pct": 0.1}]
    central_negocios_service.obter_mercado(lambda: {"indices": indices_bons, "cambio": cambio_bom}, db_session)

    # Força o cache a vencer sem apagar o valor anterior — `resetar_cache()`
    # limparia os dois, o que não simula o cenário real (TTL vencido, mas
    # o último dado bom ainda em memória).
    central_negocios_service._mercado_cache_em -= central_negocios_service._TTL_SEGUNDOS + 1

    resultado = central_negocios_service.obter_mercado(lambda: {"indices": [], "cambio": []}, db_session)

    assert resultado["indices"] == indices_bons
    assert resultado["cambio"] == cambio_bom


def test_obter_mercado_usa_dado_novo_quando_busca_funciona(db_session) -> None:
    cambio_velho = [{"codigo": "USD", "nome": "USD", "valor": 5.0, "variacao_pct": 0.1}]
    cambio_novo = [{"codigo": "USD", "nome": "USD", "valor": 5.5, "variacao_pct": 2.0}]
    central_negocios_service.obter_mercado(lambda: {"indices": [], "cambio": cambio_velho}, db_session)
    central_negocios_service._mercado_cache_em -= central_negocios_service._TTL_SEGUNDOS + 1

    resultado = central_negocios_service.obter_mercado(lambda: {"indices": [], "cambio": cambio_novo}, db_session)

    assert resultado["cambio"] == cambio_novo


def test_obter_mercado_usa_cache_persistido_quando_memoria_zera(db_session) -> None:
    """Raio-X 2026-09-24: cold start do Render zera o cache em memória
    — se a busca fresca também falhar exatamente nesse momento, o
    fallback stale precisa recorrer ao banco em vez de ficar vazio."""
    cambio_bom = [{"codigo": "USD", "nome": "USD", "valor": 5.0, "variacao_pct": 0.1}]
    central_negocios_service.obter_mercado(lambda: {"indices": [], "cambio": cambio_bom}, db_session)

    # Simula um restart de processo: cache em memória zera, mas o banco
    # (outra "sessão"/processo) já tem o valor bom persistido.
    central_negocios_service.resetar_cache()

    resultado = central_negocios_service.obter_mercado(lambda: {"indices": [], "cambio": []}, db_session)

    assert resultado["cambio"] == cambio_bom


def test_obter_mercado_persiste_no_banco_apos_sucesso(db_session) -> None:
    from app.models.cache_mercado_externo import CacheMercadoExterno

    cambio_bom = [{"codigo": "USD", "nome": "USD", "valor": 5.0, "variacao_pct": 0.1}]
    central_negocios_service.obter_mercado(lambda: {"indices": [], "cambio": cambio_bom}, db_session)

    linha = db_session.get(CacheMercadoExterno, "mercado")
    assert linha is not None
    assert linha.valor["cambio"] == cambio_bom


def test_obter_noticias_mantem_dado_antigo_quando_nova_busca_falha() -> None:
    noticias_boas = [{"portal": "UOL Economia", "titulo": "Teste", "link": "https://exemplo.com", "publicado_em": None}]
    central_negocios_service.obter_noticias(lambda: noticias_boas)
    central_negocios_service._noticias_cache_em -= central_negocios_service._TTL_SEGUNDOS + 1

    resultado = central_negocios_service.obter_noticias(lambda: [])

    assert resultado == noticias_boas


def test_obter_noticias_usa_cache_dentro_do_ttl() -> None:
    chamadas = []

    def client():
        chamadas.append(1)
        return [{"portal": "UOL Economia", "titulo": "Teste", "link": "https://exemplo.com", "publicado_em": None}]

    central_negocios_service.obter_noticias(client)
    central_negocios_service.obter_noticias(client)

    assert len(chamadas) == 1
