def test_criar_oferta_estruturada(client, criar_oferta):
    """E1-H2: cadastro estruturado de ofertas com diferenciais e provas sociais."""
    oferta = criar_oferta(diferenciais=["suporte 24h"], provas_sociais=["case Acme"])

    assert oferta["diferenciais"] == ["suporte 24h"]
    assert oferta["provas_sociais"] == ["case Acme"]
    assert oferta["ativo"] is True


def test_criar_nova_oferta_desativa_a_anterior(client, criar_oferta):
    """Bug real: cadastrar oferta nova deixava a antiga ativa também —
    `_contexto_de_geracao` da cadência pegava uma das duas por sorte."""
    primeira = criar_oferta(nome="Oferta 1")

    segunda = criar_oferta(nome="Oferta 2")

    ofertas = {o["id"]: o for o in client.get("/api/v1/ofertas").json()}
    assert ofertas[primeira["id"]]["ativo"] is False
    assert ofertas[segunda["id"]]["ativo"] is True


def test_editar_oferta(client, criar_oferta):
    oferta = criar_oferta(nome="Nome original")

    resposta = client.put(
        f"/api/v1/ofertas/{oferta['id']}",
        json={
            "nome": "Nome editado",
            "descricao": "Descrição editada",
            "diferenciais": ["novo diferencial"],
            "provas_sociais": [],
        },
    )

    assert resposta.status_code == 200
    assert resposta.json()["nome"] == "Nome editado"
    assert resposta.json()["diferenciais"] == ["novo diferencial"]


def test_ativar_oferta_desativa_as_demais(client, criar_oferta):
    primeira = criar_oferta(nome="Oferta 1")
    segunda = criar_oferta(nome="Oferta 2")  # já deixa a primeira inativa

    resposta = client.post(f"/api/v1/ofertas/{primeira['id']}/ativar")

    assert resposta.status_code == 200
    assert resposta.json()["ativo"] is True
    ofertas = {o["id"]: o for o in client.get("/api/v1/ofertas").json()}
    assert ofertas[segunda["id"]]["ativo"] is False


def test_desativar_oferta(client, criar_oferta):
    oferta = criar_oferta()

    resposta = client.post(f"/api/v1/ofertas/{oferta['id']}/desativar")

    assert resposta.status_code == 200
    assert resposta.json()["ativo"] is False


def test_excluir_oferta(client, criar_oferta):
    oferta = criar_oferta()

    resposta = client.delete(f"/api/v1/ofertas/{oferta['id']}")

    assert resposta.status_code == 204
    ofertas = client.get("/api/v1/ofertas").json()
    assert all(o["id"] != oferta["id"] for o in ofertas)


def test_excluir_oferta_remove_materiais_vinculados(client, criar_oferta):
    oferta = criar_oferta()
    client.post(
        f"/api/v1/ofertas/{oferta['id']}/materiais",
        files={"arquivo": ("apresentacao.pdf", b"%PDF-1.4 conteudo", "application/pdf")},
    )

    resposta = client.delete(f"/api/v1/ofertas/{oferta['id']}")

    assert resposta.status_code == 204


def test_upload_material_pdf_aceito(client, criar_oferta):
    """E1-H2: suporte a upload de materiais (PDF, docx) para contexto do motor."""
    oferta = criar_oferta()

    resposta = client.post(
        f"/api/v1/ofertas/{oferta['id']}/materiais",
        files={"arquivo": ("apresentacao.pdf", b"%PDF-1.4 conteudo de teste", "application/pdf")},
    )

    assert resposta.status_code == 201
    material = resposta.json()
    assert material["nome_arquivo"] == "apresentacao.pdf"
    assert material["tipo_mime"] == "application/pdf"
    assert material["tamanho_bytes"] > 0


def test_upload_material_docx_aceito(client, criar_oferta):
    oferta = criar_oferta()

    resposta = client.post(
        f"/api/v1/ofertas/{oferta['id']}/materiais",
        files={
            "arquivo": (
                "catalogo.docx",
                b"conteudo docx de teste",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert resposta.status_code == 201


def test_upload_material_tipo_invalido_e_rejeitado(client, criar_oferta):
    oferta = criar_oferta()

    resposta = client.post(
        f"/api/v1/ofertas/{oferta['id']}/materiais",
        files={"arquivo": ("imagem.png", b"conteudo", "image/png")},
    )

    assert resposta.status_code == 422
