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


def _obter_aprovacao_id(client, cadencia_id: int) -> int:
    itens = client.get("/api/v1/aprovacoes", params={"cadencia_id": cadencia_id}).json()
    return itens[0]["aprovacao_id"]


def test_correcoes_recentes_lista_edicao_e_rejeicao(
    client, onboarding_completo, criar_conta_com_decisor, criar_cadencia, fake_llm
):
    conta, _ = criar_conta_com_decisor()
    cadencia = criar_cadencia()
    fake_llm.definir_respostas(["Texto original 1", "Texto original 2", "Texto original 3", "Texto original 4", "Texto original 5"])
    client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})

    aprovacao_id_1 = _obter_aprovacao_id(client, cadencia["id"])
    editada = client.put(f"/api/v1/aprovacoes/{aprovacao_id_1}/mensagem", json={"conteudo": "Texto editado"})
    assert editada.status_code == 200

    itens = client.get("/api/v1/aprovacoes", params={"cadencia_id": cadencia["id"]}).json()
    aprovacao_id_2 = next(item["aprovacao_id"] for item in itens if item["aprovacao_id"] != aprovacao_id_1)
    rejeitada = client.post(f"/api/v1/aprovacoes/{aprovacao_id_2}/rejeitar", json={"motivo": "Muito genérico"})
    assert rejeitada.status_code == 200

    correcoes = client.get("/api/v1/regras-aprendidas/correcoes-recentes").json()

    assert len(correcoes) == 2
    edicao = next(item for item in correcoes if item["tipo"] == "edicao")
    # Toque de e-mail ganha rodapé de opt-out (`_rodape_por_canal`) antes
    # de salvar — a comparação exata não vale aqui, só a resposta pura da IA.
    assert edicao["conteudo_anterior"].startswith("Texto original 1")
    assert edicao["conteudo_novo"] == "Texto editado"
    assert edicao["icp_id"] == cadencia["icp_id"]
    assert edicao["oferta_id"] == cadencia["oferta_id"]
    rejeicao = next(item for item in correcoes if item["tipo"] == "rejeicao")
    assert rejeicao["motivo"] == "Muito genérico"


def test_sugerir_regra_com_ia_retorna_texto_sugerido(
    client, onboarding_completo, criar_conta_com_decisor, criar_cadencia, fake_llm
):
    conta, _ = criar_conta_com_decisor()
    cadencia = criar_cadencia()
    fake_llm.definir_respostas(["Texto original"] * 5)
    client.post(f"/api/v1/cadencias/{cadencia['id']}/gerar", json={"conta_ids": [conta.id]})
    aprovacao_id = _obter_aprovacao_id(client, cadencia["id"])
    client.put(f"/api/v1/aprovacoes/{aprovacao_id}/mensagem", json={"conteudo": "Texto editado"})
    correcao = client.get("/api/v1/regras-aprendidas/correcoes-recentes").json()[0]

    fake_llm.definir_respostas(["Nunca usar a palavra sinergia"])
    resposta = client.post(f"/api/v1/regras-aprendidas/correcoes-recentes/{correcao['id']}/sugerir-regra")

    assert resposta.status_code == 200
    assert resposta.json()["regra_sugerida"] == "Nunca usar a palavra sinergia"


def test_sugerir_regra_com_ia_correcao_inexistente_retorna_404(client, onboarding_completo):
    resposta = client.post("/api/v1/regras-aprendidas/correcoes-recentes/9999/sugerir-regra")
    assert resposta.status_code == 404
