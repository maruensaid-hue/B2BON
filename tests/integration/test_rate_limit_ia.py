def test_sexta_chamada_de_ia_em_5_minutos_retorna_429(client):
    """Fase 7A, hardening — sem isto, nenhuma rota de IA tinha teto de
    custo/abuso (§85 Cost Governance)."""
    client.put("/api/v1/agente-corporativo/modo", json={"modo": "interno"})

    for _ in range(20):
        resposta = client.post("/api/v1/agente-corporativo/testar", json={"pergunta": "pergunta sem match nenhum"})
        assert resposta.status_code == 200

    resposta_21 = client.post("/api/v1/agente-corporativo/testar", json={"pergunta": "pergunta sem match nenhum"})

    assert resposta_21.status_code == 429
