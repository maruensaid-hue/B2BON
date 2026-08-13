def test_obter_template_cria_se_nao_existir_via_api(client):
    resposta = client.get("/api/v1/template-proposta")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["mostrar_tabela_produtos"] is True
    assert corpo["mostrar_tabela_servicos"] is True


def test_atualizar_template_via_api(client):
    resposta = client.put(
        "/api/v1/template-proposta",
        json={
            "texto_introdutorio": "Somos a empresa X",
            "termo_aceite": "Termo",
            "mostrar_tabela_produtos": True,
            "mostrar_tabela_servicos": False,
        },
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["texto_introdutorio"] == "Somos a empresa X"
    assert corpo["mostrar_tabela_servicos"] is False


def test_enviar_e_baixar_logo_via_api(client):
    enviada = client.post(
        "/api/v1/template-proposta/logo",
        files={"arquivo": ("logo.png", b"fake-png-bytes", "image/png")},
    )
    assert enviada.status_code == 200
    assert enviada.json()["logo_tipo_mime"] == "image/png"

    baixada = client.get("/api/v1/template-proposta/logo")
    assert baixada.status_code == 200
    assert baixada.content == b"fake-png-bytes"


def test_enviar_logo_tipo_invalido_falha_via_api(client):
    resposta = client.post(
        "/api/v1/template-proposta/logo",
        files={"arquivo": ("logo.pdf", b"x", "application/pdf")},
    )

    assert resposta.status_code == 422


def test_crud_itens_via_api(client):
    criado = client.post("/api/v1/template-proposta/itens", json={"tipo": "produto", "descricao": "Licença", "valor": 500.0})
    assert criado.status_code == 201
    item_id = criado.json()["id"]

    listagem = client.get("/api/v1/template-proposta/itens?tipo=produto").json()
    assert len(listagem) == 1

    atualizado = client.put(f"/api/v1/template-proposta/itens/{item_id}", json={"descricao": "Licença Pro", "valor": 700.0})
    assert atualizado.status_code == 200
    assert atualizado.json()["descricao"] == "Licença Pro"

    removido = client.delete(f"/api/v1/template-proposta/itens/{item_id}")
    assert removido.status_code == 204
    assert client.get("/api/v1/template-proposta/itens?tipo=produto").json() == []


def test_adicionar_item_tipo_invalido_falha_via_api(client):
    resposta = client.post("/api/v1/template-proposta/itens", json={"tipo": "invalido", "descricao": "X", "valor": 1.0})

    assert resposta.status_code == 422
