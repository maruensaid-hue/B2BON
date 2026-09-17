TENANT_B = "tenant-outro"


def test_declarar_e_listar_relacionamento_via_api(client):
    resposta = client.post(
        "/api/v1/rede-social/relacionamentos", json={"tenant_id_destino": TENANT_B, "tipo": "SUPPLIER_OF"}
    )

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["tipo"] == "SUPPLIER_OF"
    assert corpo["confianca"] == "autodeclarada"

    listagem = client.get("/api/v1/rede-social/relacionamentos/tenant-teste").json()
    assert len(listagem) == 1


def test_contraparte_confirma_via_api(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    declarado = client.post(
        "/api/v1/rede-social/relacionamentos", json={"tenant_id_destino": TENANT_B, "tipo": "PARTNER_OF"}
    ).json()

    resposta = client.post(f"/api/v1/rede-social/relacionamentos/{declarado['id']}/confirmar", headers=headers_b)

    assert resposta.status_code == 200
    assert resposta.json()["confianca"] == "confirmada_pela_contraparte"


def test_terceiro_nao_pode_confirmar_via_api(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    declarado = client.post(
        "/api/v1/rede-social/relacionamentos", json={"tenant_id_destino": TENANT_B, "tipo": "PARTNER_OF"}
    ).json()

    resposta = client.post(f"/api/v1/rede-social/relacionamentos/{declarado['id']}/confirmar")

    assert resposta.status_code == 403


def test_remover_relacionamento_via_api(client):
    declarado = client.post(
        "/api/v1/rede-social/relacionamentos", json={"tenant_id_destino": TENANT_B, "tipo": "SUPPLIER_OF"}
    ).json()

    resposta = client.delete(f"/api/v1/rede-social/relacionamentos/{declarado['id']}")

    assert resposta.status_code == 204
    assert client.get("/api/v1/rede-social/relacionamentos/tenant-teste").json() == []
