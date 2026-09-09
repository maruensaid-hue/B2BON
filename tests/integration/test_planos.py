def _payload_plano(nome: str = "Plano Novo", **overrides) -> dict:
    dados = {
        "nome": nome,
        "franquia_contas_mes": 100,
        "max_usuarios": 5,
        "preco_mensal": 199.0,
        "visivel_self_service": True,
        "limite_enriquecimento_site_semanal": 25,
        "limite_enriquecimento_contatos_semanal": 25,
        "permite_ab_teste_cadencia": False,
        "permite_auto_aprovacao": False,
        "permite_webhook_relatorio": False,
        "permite_api_parceiros": False,
        "permite_subtenants": False,
        "retencao_dias_relatorio": None,
        "retencao_dias_auditoria": None,
    }
    dados.update(overrides)
    return dados


def test_super_admin_cria_plano(client):
    resposta = client.post("/api/v1/planos", json=_payload_plano("Plano Criado Via API"))

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["nome"] == "Plano Criado Via API"
    assert corpo["permite_ab_teste_cadencia"] is False


def test_criar_plano_com_recursos_habilitados(client):
    resposta = client.post(
        "/api/v1/planos",
        json=_payload_plano(
            "Plano Enterprise Via API",
            permite_ab_teste_cadencia=True,
            permite_auto_aprovacao=True,
            retencao_dias_relatorio=None,
        ),
    )

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["permite_ab_teste_cadencia"] is True
    assert corpo["permite_auto_aprovacao"] is True


def test_criar_plano_com_nome_duplicado_recusa(client):
    client.post("/api/v1/planos", json=_payload_plano("Plano Duplicado"))

    resposta = client.post("/api/v1/planos", json=_payload_plano("Plano Duplicado"))

    assert resposta.status_code == 409


def test_criar_plano_com_valor_negativo_recusa(client):
    resposta = client.post("/api/v1/planos", json=_payload_plano("Plano Negativo", max_usuarios=-1))

    assert resposta.status_code == 422


def test_atualizar_plano(client):
    criado = client.post("/api/v1/planos", json=_payload_plano("Plano Pra Editar")).json()

    resposta = client.put(
        f"/api/v1/planos/{criado['id']}",
        json=_payload_plano("Plano Pra Editar", max_usuarios=50, permite_subtenants=True),
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["max_usuarios"] == 50
    assert corpo["permite_subtenants"] is True


def test_atualizar_plano_inexistente_falha(client):
    resposta = client.put("/api/v1/planos/999999", json=_payload_plano("Não Existe"))

    assert resposta.status_code == 404


def test_usuario_comum_nao_pode_criar_plano(client, criar_usuario_autenticado):
    headers = criar_usuario_autenticado("outro-tenant-planos", papel="admin")

    resposta = client.post("/api/v1/planos", json=_payload_plano("Plano Não Autorizado"), headers=headers)

    assert resposta.status_code == 403


def test_lista_planos_traz_todos_os_campos_novos(client):
    client.post("/api/v1/planos", json=_payload_plano("Plano Listagem Completa", permite_api_parceiros=True))

    lista = client.get("/api/v1/planos", headers={"Authorization": ""}).json()

    plano = next(p for p in lista if p["nome"] == "Plano Listagem Completa")
    assert plano["permite_api_parceiros"] is True
    assert "retencao_dias_auditoria" in plano
