import io

from PIL import Image

TENANT_B = "tenant-outro"


def _imagem_jpeg_bytes() -> bytes:
    imagem = Image.new("RGB", (400, 300), color=(10, 20, 30))
    saida = io.BytesIO()
    imagem.save(saida, format="JPEG")
    return saida.getvalue()


def test_criar_e_listar_post_via_api(client):
    # `texto`/`link_url` viraram Form fields (não mais JSON) desde que o
    # endpoint aceita anexo real de foto/vídeo via multipart.
    resposta = client.post("/api/v1/rede-social/posts", data={"texto": "Olá, rede!"})

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["texto"] == "Olá, rede!"
    assert corpo["midias"] == []

    feed = client.get("/api/v1/rede-social/posts").json()
    assert len(feed) == 1
    assert feed[0]["texto"] == "Olá, rede!"


def test_criar_post_com_foto_anexada_via_api(client):
    resposta = client.post(
        "/api/v1/rede-social/posts",
        data={"texto": "Post com foto"},
        files=[("arquivos", ("foto.jpg", _imagem_jpeg_bytes(), "image/jpeg"))],
    )

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert len(corpo["midias"]) == 1
    assert corpo["midias"][0]["tipo"] == "imagem"
    midia_id = corpo["midias"][0]["id"]
    assert corpo["midias"][0]["url"] == f"/rede-social/posts/{corpo['id']}/midia/{midia_id}"

    midia = client.get(f"/api/v1/rede-social/posts/{corpo['id']}/midia/{midia_id}")
    assert midia.status_code == 200
    assert midia.headers["content-type"] == "image/jpeg"
    assert len(midia.content) > 0


def test_criar_post_com_carrossel_de_fotos_via_api(client):
    arquivos = [
        ("arquivos", ("foto1.jpg", _imagem_jpeg_bytes(), "image/jpeg")),
        ("arquivos", ("foto2.jpg", _imagem_jpeg_bytes(), "image/jpeg")),
        ("arquivos", ("foto3.jpg", _imagem_jpeg_bytes(), "image/jpeg")),
    ]

    resposta = client.post("/api/v1/rede-social/posts", data={"texto": "Carrossel"}, files=arquivos)

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert len(corpo["midias"]) == 3
    assert all(midia["tipo"] == "imagem" for midia in corpo["midias"])


def test_criar_post_com_video_e_foto_juntos_retorna_erro(client):
    arquivos = [
        ("arquivos", ("foto.jpg", _imagem_jpeg_bytes(), "image/jpeg")),
        ("arquivos", ("video.mp4", b"video falso", "video/mp4")),
    ]

    resposta = client.post("/api/v1/rede-social/posts", data={"texto": "Inválido"}, files=arquivos)

    assert resposta.status_code == 422


def test_criar_post_com_arquivo_tipo_nao_suportado_retorna_erro(client):
    resposta = client.post(
        "/api/v1/rede-social/posts",
        data={"texto": "Post com PDF"},
        files=[("arquivos", ("doc.pdf", b"%PDF-1.4 conteudo", "application/pdf"))],
    )

    assert resposta.status_code == 422


def test_baixar_midia_de_post_sem_anexo_retorna_404(client):
    post = client.post("/api/v1/rede-social/posts", data={"texto": "Sem mídia"}).json()

    resposta = client.get(f"/api/v1/rede-social/posts/{post['id']}/midia/1")

    assert resposta.status_code == 404


def test_feed_mostra_posts_de_outros_tenants(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    client.post("/api/v1/rede-social/posts", data={"texto": "Post da empresa B"}, headers=headers_b)
    client.post("/api/v1/rede-social/posts", data={"texto": "Post da empresa A"})

    feed = client.get("/api/v1/rede-social/posts").json()

    assert len(feed) == 2


def test_excluir_post_de_outro_tenant_retorna_403(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    post = client.post("/api/v1/rede-social/posts", data={"texto": "Meu post"}).json()

    resposta = client.delete(f"/api/v1/rede-social/posts/{post['id']}", headers=headers_b)

    assert resposta.status_code == 403


def test_excluir_post_proprio_via_api(client):
    post = client.post("/api/v1/rede-social/posts", data={"texto": "Apagar"}).json()

    resposta = client.delete(f"/api/v1/rede-social/posts/{post['id']}")

    assert resposta.status_code == 204
    assert client.get("/api/v1/rede-social/posts").json() == []


def test_comentar_e_listar_comentarios_via_api(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    post = client.post("/api/v1/rede-social/posts", data={"texto": "Post com comentário"}).json()

    resposta = client.post(
        f"/api/v1/rede-social/posts/{post['id']}/comentarios", json={"texto": "Muito bom!"}, headers=headers_b
    )

    assert resposta.status_code == 201
    assert resposta.json()["texto"] == "Muito bom!"

    comentarios = client.get(f"/api/v1/rede-social/posts/{post['id']}/comentarios").json()
    assert len(comentarios) == 1
    assert comentarios[0]["texto"] == "Muito bom!"


def test_reagir_toggle_via_api(client):
    post = client.post("/api/v1/rede-social/posts", data={"texto": "Post com reação"}).json()

    resposta_1 = client.post(f"/api/v1/rede-social/posts/{post['id']}/reagir")
    assert resposta_1.json() == {"reagiu": True, "total": 1}

    resposta_2 = client.post(f"/api/v1/rede-social/posts/{post['id']}/reagir")
    assert resposta_2.json() == {"reagiu": False, "total": 0}


def test_feed_traz_contagens_e_eu_reagi_via_api(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    post = client.post("/api/v1/rede-social/posts", data={"texto": "Post"}).json()
    client.post(f"/api/v1/rede-social/posts/{post['id']}/comentarios", json={"texto": "Oi"}, headers=headers_b)
    client.post(f"/api/v1/rede-social/posts/{post['id']}/reagir", headers=headers_b)

    feed_b = client.get("/api/v1/rede-social/posts", headers=headers_b).json()
    feed_a = client.get("/api/v1/rede-social/posts").json()

    assert feed_b[0]["total_comentarios"] == 1
    assert feed_b[0]["total_reacoes"] == 1
    assert feed_b[0]["eu_reagi"] is True
    assert feed_a[0]["eu_reagi"] is False
