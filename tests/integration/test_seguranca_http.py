def test_cabecalhos_de_seguranca_presentes_em_toda_resposta(client):
    resposta = client.get("/api/v1/icp")

    assert resposta.headers["x-content-type-options"] == "nosniff"
    assert resposta.headers["x-frame-options"] == "DENY"
    assert resposta.headers["referrer-policy"] == "strict-origin-when-cross-origin"
