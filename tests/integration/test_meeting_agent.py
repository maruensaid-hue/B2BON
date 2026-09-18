def _criar_negocio_via_api(client) -> int:
    conta = client.post("/api/v1/leads/contas", json={"nome": "Conta Meeting"}).json()
    decisor = client.post(f"/api/v1/contas/{conta['id']}/decisores", json={"nome": "Decisor Teste", "cargo": "Diretor"}).json()
    negocio = client.post(
        "/api/v1/crm/negocios",
        json={"conta_id": conta["id"], "decisor_id": decisor["id"], "nome": "Negócio via API", "valor": 5000},
    ).json()
    return negocio["id"]


def test_gerar_meeting_brief_via_api(client):
    negocio_id = _criar_negocio_via_api(client)

    resposta = client.post(f"/api/v1/crm/negocios/{negocio_id}/meeting-brief")

    assert resposta.status_code == 200
    assert "brief" in resposta.json()


def test_gerar_meeting_brief_negocio_inexistente_retorna_404(client):
    resposta = client.post("/api/v1/crm/negocios/9999/meeting-brief")

    assert resposta.status_code == 404
