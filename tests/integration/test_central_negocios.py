def test_obter_mercado_e_publico_sem_autenticacao(client):
    resposta = client.get("/api/v1/central-negocios/mercado", headers={"Authorization": ""})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["indices"][0]["nome"] == "Ibovespa"
    assert corpo["indices"][0]["serie"][0]["valor"] == 130000.5
    assert corpo["cambio"][0]["codigo"] == "USD"
    assert corpo["cambio"][1]["nome"] == "Bitcoin"


def test_obter_noticias_e_publico_sem_autenticacao(client):
    resposta = client.get("/api/v1/central-negocios/noticias", headers={"Authorization": ""})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo[0]["portal"] == "UOL Economia"
    assert corpo[0]["link"] == "https://exemplo.com/1"
