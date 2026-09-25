TENANT_ID = "tenant-teste"


def _payload(**overrides) -> dict:
    dados = {
        "nome": "Fulano Vendedor",
        "email": "fulano@vendedor.com.br",
        "cpf": "123.456.789-00",
        "chave_pix": "fulano@pix.com.br",
        "percentual_comissao": 0.1,
    }
    dados.update(overrides)
    return dados


def test_super_admin_cria_representante(client):
    resposta = client.post("/api/v1/representantes", json=_payload())

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["nome"] == "Fulano Vendedor"
    assert corpo["ativo"] is True


def test_admin_comum_nao_pode_criar_representante(client, criar_usuario_autenticado):
    headers = criar_usuario_autenticado(TENANT_ID, papel="admin", email="admin-comum@teste.com.br")

    resposta = client.post("/api/v1/representantes", json=_payload(email="outro@vendedor.com.br"), headers=headers)

    assert resposta.status_code == 403


def test_percentual_comissao_invalido_e_recusado(client):
    resposta = client.post("/api/v1/representantes", json=_payload(percentual_comissao=1.5))

    assert resposta.status_code in (400, 409, 422)


def test_listar_self_service_nao_exige_autenticacao_e_esconde_pix(client):
    client.post("/api/v1/representantes", json=_payload())

    resposta = client.get("/api/v1/representantes/self-service", headers={})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert len(corpo) >= 1
    assert "chave_pix" not in corpo[0]
    assert "cpf" not in corpo[0]


def test_listar_self_service_esconde_representante_inativo(client):
    criado = client.post("/api/v1/representantes", json=_payload(email="inativo@vendedor.com.br")).json()
    client.put(
        f"/api/v1/representantes/{criado['id']}",
        json={**_payload(email="inativo@vendedor.com.br"), "ativo": False},
    )

    resposta = client.get("/api/v1/representantes/self-service")

    assert not any(r["id"] == criado["id"] for r in resposta.json())


def test_atualizar_representante(client):
    criado = client.post("/api/v1/representantes", json=_payload()).json()

    resposta = client.put(
        f"/api/v1/representantes/{criado['id']}",
        json={**_payload(), "nome": "Nome Atualizado", "ativo": True},
    )

    assert resposta.status_code == 200
    assert resposta.json()["nome"] == "Nome Atualizado"
