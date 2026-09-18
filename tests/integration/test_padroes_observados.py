def test_padroes_observados_via_api_sem_dados(client):
    resposta = client.get("/api/v1/regras-aprendidas/padroes-observados")

    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["ticket_medio"] is None
    assert dados["amostra_ticket_medio"] == 0
