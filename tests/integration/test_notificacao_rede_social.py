TENANT_B = "tenant-outro"


def test_listar_notificacoes_via_api(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    client.post("/api/v1/rede-social/conexoes", json={"tenant_id_destino": TENANT_B})

    notificacoes = client.get("/api/v1/rede-social/notificacoes", headers=headers_b).json()

    assert len(notificacoes) == 1
    assert notificacoes[0]["tipo"] == "connection_request"
    assert notificacoes[0]["lida"] is False


def test_contagem_nao_lidas_via_api(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    client.post("/api/v1/rede-social/conexoes", json={"tenant_id_destino": TENANT_B})

    contagem = client.get("/api/v1/rede-social/notificacoes/contagem-nao-lidas", headers=headers_b).json()

    assert contagem["total"] == 1


def test_marcar_lida_via_api(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    client.post("/api/v1/rede-social/conexoes", json={"tenant_id_destino": TENANT_B})
    notificacao = client.get("/api/v1/rede-social/notificacoes", headers=headers_b).json()[0]

    resposta = client.post(f"/api/v1/rede-social/notificacoes/{notificacao['id']}/marcar-lida", headers=headers_b)

    assert resposta.status_code == 204
    contagem = client.get("/api/v1/rede-social/notificacoes/contagem-nao-lidas", headers=headers_b).json()
    assert contagem["total"] == 0


def test_marcar_todas_lidas_via_api(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    client.post("/api/v1/rede-social/conexoes", json={"tenant_id_destino": TENANT_B})

    resposta = client.post("/api/v1/rede-social/notificacoes/marcar-todas-lidas", headers=headers_b)

    assert resposta.status_code == 204
    contagem = client.get("/api/v1/rede-social/notificacoes/contagem-nao-lidas", headers=headers_b).json()
    assert contagem["total"] == 0


def test_notificacoes_isoladas_por_tenant(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    client.post("/api/v1/rede-social/conexoes", json={"tenant_id_destino": TENANT_B})

    notificacoes_a = client.get("/api/v1/rede-social/notificacoes").json()

    assert notificacoes_a == []
