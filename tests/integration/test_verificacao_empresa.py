TENANT_B = "tenant-outro"


def test_solicitar_verificacao_via_api(client):
    client.put("/api/v1/rede-social/perfil", json={"site": "https://acme.com.br"})

    resposta = client.post("/api/v1/verificacao-empresa", json={"email_verificacao": "ana@acme.com.br"})

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["status"] == "pendente"
    assert corpo["dominio_confere"] is True


def test_super_admin_lista_e_revisa_pendentes(client):
    """A fixture `client` já loga como super_admin (tenant-teste) — mesmo
    tenant que solicita, mesmo usuário que revisa, aqui só pra provar o
    fluxo ponta a ponta via API."""
    client.post("/api/v1/verificacao-empresa", json={"email_verificacao": "ana@acme.com.br"})

    pendentes = client.get("/api/v1/verificacao-empresa/pendentes").json()
    assert len(pendentes) == 1
    verificacao_id = pendentes[0]["id"]

    revisada = client.post(f"/api/v1/verificacao-empresa/{verificacao_id}/revisar", json={"aprovar": True})

    assert revisada.status_code == 200
    assert revisada.json()["status"] == "aprovada"

    perfil = client.get("/api/v1/rede-social/perfil").json()
    assert perfil["status_verificacao"] == "verificada"


def test_usuario_comum_nao_pode_listar_pendentes(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")

    resposta = client.get("/api/v1/verificacao-empresa/pendentes", headers=headers_b)

    assert resposta.status_code == 403


def test_usuario_comum_nao_pode_revisar(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    client.post("/api/v1/verificacao-empresa", json={"email_verificacao": "ana@acme.com.br"})
    verificacao_id = client.get("/api/v1/verificacao-empresa/pendentes").json()[0]["id"]

    resposta = client.post(
        f"/api/v1/verificacao-empresa/{verificacao_id}/revisar", json={"aprovar": True}, headers=headers_b
    )

    assert resposta.status_code == 403
