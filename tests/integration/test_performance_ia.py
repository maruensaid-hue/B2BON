def test_performance_ia_via_api_sem_dados(client):
    resposta = client.get("/api/v1/regras-aprendidas/performance-ia")

    assert resposta.status_code == 200
    dados = resposta.json()
    assert dados["total_propostas"] == 0
    assert dados["taxa_aceitacao"] == 0.0
