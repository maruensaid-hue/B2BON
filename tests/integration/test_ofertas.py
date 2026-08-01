def test_criar_oferta_estruturada(client, criar_oferta):
    """E1-H2: cadastro estruturado de ofertas com diferenciais e provas sociais."""
    oferta = criar_oferta(diferenciais=["suporte 24h"], provas_sociais=["case Acme"])

    assert oferta["diferenciais"] == ["suporte 24h"]
    assert oferta["provas_sociais"] == ["case Acme"]
    assert oferta["ativo"] is True


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
