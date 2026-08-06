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


def test_baixar_material_devolve_o_conteudo_enviado(client, criar_oferta):
    """Raio-X de produção: material vive só no disco efêmero do Render e
    some a cada redeploy — agora é blob no banco, e nunca existiu um
    endpoint de download antes disto."""
    oferta = criar_oferta()
    conteudo_original = b"%PDF-1.4 conteudo de teste para baixar depois"
    material = client.post(
        f"/api/v1/ofertas/{oferta['id']}/materiais",
        files={"arquivo": ("apresentacao.pdf", conteudo_original, "application/pdf")},
    ).json()

    resposta = client.get(f"/api/v1/ofertas/{oferta['id']}/materiais/{material['id']}")

    assert resposta.status_code == 200
    assert resposta.content == conteudo_original
    assert resposta.headers["content-type"] == "application/pdf"


def test_upload_material_acima_do_limite_e_rejeitado(client, criar_oferta):
    """DoS de armazenamento: antes não havia nenhum teto de tamanho."""
    oferta = criar_oferta()
    conteudo_gigante = b"0" * (15 * 1024 * 1024 + 1)

    resposta = client.post(
        f"/api/v1/ofertas/{oferta['id']}/materiais",
        files={"arquivo": ("gigante.pdf", conteudo_gigante, "application/pdf")},
    )

    assert resposta.status_code == 422


def test_upload_material_com_nome_de_path_traversal_nao_escapa_o_registro(client, criar_oferta):
    """Antes, o nome do arquivo entrava direto num Path(...) / nome_arquivo
    — um nome como "../../etc/passwd" escapava do diretório pretendido.
    Guardar como blob elimina a superfície inteira: não existe mais path
    nenhum sendo montado a partir de entrada do usuário."""
    oferta = criar_oferta()

    resposta = client.post(
        f"/api/v1/ofertas/{oferta['id']}/materiais",
        files={"arquivo": ("../../../etc/passwd", b"%PDF-1.4 x", "application/pdf")},
    )

    assert resposta.status_code == 201
    material_id = resposta.json()["id"]
    baixado = client.get(f"/api/v1/ofertas/{oferta['id']}/materiais/{material_id}")
    assert baixado.content == b"%PDF-1.4 x"
