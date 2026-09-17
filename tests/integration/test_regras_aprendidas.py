def test_criar_listar_atualizar_regra_aprendida(client, onboarding_completo, criar_icp, criar_oferta):
    icp = criar_icp(nome="ICP Regra")
    oferta = criar_oferta(nome="Oferta Regra")

    resposta = client.post(
        "/api/v1/regras-aprendidas",
        json={"icp_id": icp["id"], "oferta_id": oferta["id"], "canal": "email", "regra": "Nunca usar 'sinergia'"},
    )
    assert resposta.status_code == 201
    regra = resposta.json()
    assert regra["ativa"] is True

    listagem = client.get("/api/v1/regras-aprendidas").json()
    assert len(listagem) == 1

    atualizada = client.put(
        f"/api/v1/regras-aprendidas/{regra['id']}",
        json={"icp_id": icp["id"], "oferta_id": oferta["id"], "canal": "email", "regra": "Nunca usar 'disruptivo'"},
    )
    assert atualizada.status_code == 200
    assert atualizada.json()["regra"] == "Nunca usar 'disruptivo'"


def test_ativar_desativar_excluir_regra_aprendida(client, onboarding_completo):
    regra = client.post("/api/v1/regras-aprendidas", json={"regra": "Regra qualquer"}).json()

    desativada = client.post(f"/api/v1/regras-aprendidas/{regra['id']}/desativar")
    assert desativada.json()["ativa"] is False

    reativada = client.post(f"/api/v1/regras-aprendidas/{regra['id']}/ativar")
    assert reativada.json()["ativa"] is True

    excluida = client.delete(f"/api/v1/regras-aprendidas/{regra['id']}")
    assert excluida.status_code == 204
    assert client.get("/api/v1/regras-aprendidas").json() == []


def test_regra_inexistente_retorna_404(client, onboarding_completo):
    resposta = client.post("/api/v1/regras-aprendidas/9999/desativar")
    assert resposta.status_code == 404
