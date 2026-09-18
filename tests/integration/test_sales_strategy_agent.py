def test_sugerir_estrategia_venda_via_api(client):
    conta = client.post("/api/v1/leads/contas", json={"nome": "Conta Estrategia"}).json()

    resposta = client.post(f"/api/v1/contas/{conta['id']}/estrategia-venda")

    assert resposta.status_code == 200
    assert "estrategia" in resposta.json()


def test_sugerir_estrategia_venda_conta_inexistente_retorna_404(client):
    resposta = client.post("/api/v1/contas/9999/estrategia-venda")

    assert resposta.status_code == 404
