TENANT_B = "tenant-outro"


def _criar_conta_e_decisor(client, cargo: str | None = None) -> tuple[int, int]:
    conta = client.post("/api/v1/leads/contas", json={"nome": "Conta Teste"}).json()
    dados = {"nome": "Decisor Teste"}
    if cargo:
        dados["cargo"] = cargo
    decisor = client.post(f"/api/v1/contas/{conta['id']}/decisores", json=dados).json()
    return conta["id"], decisor["id"]


def test_listar_decisores_traz_papel_sugerido(client, criar_usuario_autenticado):
    conta_id, decisor_id = _criar_conta_e_decisor(client, cargo="Diretor Financeiro")

    decisores = client.get(f"/api/v1/contas/{conta_id}/decisores").json()

    decisor = next(d for d in decisores if d["id"] == decisor_id)
    assert decisor["papel_sugerido"] == "ECONOMIC_BUYER"
    assert decisor["papel_confirmado"] is None


def test_confirmar_papel_decisor_via_api(client, criar_usuario_autenticado):
    conta_id, decisor_id = _criar_conta_e_decisor(client, cargo="Diretor Financeiro")

    resposta = client.post(
        f"/api/v1/contas/{conta_id}/decisores/{decisor_id}/papel", json={"papel": "ECONOMIC_BUYER"}
    )
    assert resposta.status_code == 200
    assert resposta.json()["papel_confirmado"] == "ECONOMIC_BUYER"

    decisores = client.get(f"/api/v1/contas/{conta_id}/decisores").json()
    decisor = next(d for d in decisores if d["id"] == decisor_id)
    assert decisor["papel_confirmado"] == "ECONOMIC_BUYER"


def test_confirmar_papel_invalido_retorna_erro(client, criar_usuario_autenticado):
    conta_id, decisor_id = _criar_conta_e_decisor(client)

    resposta = client.post(
        f"/api/v1/contas/{conta_id}/decisores/{decisor_id}/papel", json={"papel": "PAPEL_INEXISTENTE"}
    )
    assert resposta.status_code == 422


def test_confirmar_papel_decisor_de_outro_tenant_retorna_404(client, criar_usuario_autenticado):
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@empresab.com.br")
    conta_id, decisor_id = _criar_conta_e_decisor(client)

    resposta = client.post(
        f"/api/v1/contas/{conta_id}/decisores/{decisor_id}/papel",
        json={"papel": "ECONOMIC_BUYER"},
        headers=headers_b,
    )
    assert resposta.status_code == 404
