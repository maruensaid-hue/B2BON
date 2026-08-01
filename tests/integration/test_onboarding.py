def test_onboarding_orienta_passos_faltantes(client):
    resposta = client.get("/api/v1/onboarding/status")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["pronto_para_prospeccao"] is False
    assert len(corpo["orientacao"]) == 3


def test_onboarding_pronto_apos_icp_oferta_e_comunicacao(client, criar_icp, criar_oferta):
    """E1-H2: ao menos 1 oferta obrigatória para o onboarding avançar."""
    criar_icp()
    criar_oferta()
    client.put("/api/v1/comunicacao", json={"tom": "consultivo", "restricoes": []})

    resposta = client.get("/api/v1/onboarding/status")

    corpo = resposta.json()
    assert corpo["icp_ativo"] is True
    assert corpo["oferta_cadastrada"] is True
    assert corpo["comunicacao_configurada"] is True
    assert corpo["pronto_para_prospeccao"] is True
    assert corpo["orientacao"] == []
