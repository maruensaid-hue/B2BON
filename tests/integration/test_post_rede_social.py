TENANT_B = "tenant-outro"


def test_criar_e_listar_post_via_api(client):
    resposta = client.post("/api/v1/rede-social/posts", json={"texto": "Olá, rede!"})

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["texto"] == "Olá, rede!"

    feed = client.get("/api/v1/rede-social/posts").json()
    assert len(feed) == 1
    assert feed[0]["texto"] == "Olá, rede!"


def test_feed_mostra_posts_de_outros_tenants(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    client.post("/api/v1/rede-social/posts", json={"texto": "Post da empresa B"}, headers=headers_b)
    client.post("/api/v1/rede-social/posts", json={"texto": "Post da empresa A"})

    feed = client.get("/api/v1/rede-social/posts").json()

    assert len(feed) == 2


def test_excluir_post_de_outro_tenant_retorna_403(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    post = client.post("/api/v1/rede-social/posts", json={"texto": "Meu post"}).json()

    resposta = client.delete(f"/api/v1/rede-social/posts/{post['id']}", headers=headers_b)

    assert resposta.status_code == 403


def test_excluir_post_proprio_via_api(client):
    post = client.post("/api/v1/rede-social/posts", json={"texto": "Apagar"}).json()

    resposta = client.delete(f"/api/v1/rede-social/posts/{post['id']}")

    assert resposta.status_code == 204
    assert client.get("/api/v1/rede-social/posts").json() == []
