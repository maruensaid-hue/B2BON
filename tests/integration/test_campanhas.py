from app.services import campanha_service


def _criar_decisor(client) -> int:
    conta = client.post("/api/v1/leads/contas", json={"nome": "Empresa Campanha"}).json()
    decisor = client.post(
        f"/api/v1/contas/{conta['id']}/decisores",
        json={"nome": "Fulano", "email": "fulano@teste.com", "telefone": "11999990000"},
    ).json()
    return decisor["id"]


def test_criar_campanha_sem_canal_falha(client):
    resposta = client.post("/api/v1/campanhas", json={"nome": "Teste", "tipo": "marketing", "canais": []})
    assert resposta.status_code == 422


def test_fluxo_completo_campanha_email(client, fake_email):
    decisor_id = _criar_decisor(client)

    criada = client.post(
        "/api/v1/campanhas",
        json={
            "nome": "Campanha de teste",
            "tipo": "marketing",
            "canais": ["email"],
            "assunto": "Assunto",
            "conteudo_email": "Corpo do e-mail",
        },
    )
    assert criada.status_code == 201
    campanha_id = criada.json()["id"]
    assert criada.json()["status"] == "rascunho"

    adicionados = client.post(
        f"/api/v1/campanhas/{campanha_id}/destinatarios/decisores", json={"decisor_ids": [decisor_id]}
    )
    assert adicionados.status_code == 201
    assert len(adicionados.json()) == 1

    avulsos = client.post(
        f"/api/v1/campanhas/{campanha_id}/destinatarios/avulsos",
        json={"destinatarios": [{"nome": "Beltrano", "email": "beltrano@teste.com"}]},
    )
    assert avulsos.status_code == 201

    pronta = client.post(f"/api/v1/campanhas/{campanha_id}/marcar-pronta")
    assert pronta.status_code == 200
    assert pronta.json()["status"] == "pronta"

    detalhe = client.get(f"/api/v1/campanhas/{campanha_id}")
    assert detalhe.status_code == 200
    assert detalhe.json()["metricas"]["total"] == 2
    assert detalhe.json()["metricas"]["pendente"] == 2


def test_marcar_pronta_sem_destinatario_falha(client):
    criada = client.post(
        "/api/v1/campanhas",
        json={"nome": "Vazia", "tipo": "marketing", "canais": ["email"], "assunto": "A", "conteudo_email": "B"},
    ).json()

    resposta = client.post(f"/api/v1/campanhas/{criada['id']}/marcar-pronta")
    assert resposta.status_code == 422


def test_excluir_campanha_em_rascunho(client):
    criada = client.post(
        "/api/v1/campanhas",
        json={"nome": "Descartável", "tipo": "vendas", "canais": ["email"], "assunto": "A", "conteudo_email": "B"},
    ).json()

    resposta = client.delete(f"/api/v1/campanhas/{criada['id']}")
    assert resposta.status_code == 204
    assert client.get(f"/api/v1/campanhas/{criada['id']}").status_code == 404


def test_remover_destinatario(client):
    decisor_id = _criar_decisor(client)
    criada = client.post(
        "/api/v1/campanhas",
        json={"nome": "Campanha", "tipo": "marketing", "canais": ["email"], "assunto": "A", "conteudo_email": "B"},
    ).json()
    destinatario = client.post(
        f"/api/v1/campanhas/{criada['id']}/destinatarios/decisores", json={"decisor_ids": [decisor_id]}
    ).json()[0]

    resposta = client.delete(f"/api/v1/campanhas/{criada['id']}/destinatarios/{destinatario['id']}")
    assert resposta.status_code == 204
    detalhe = client.get(f"/api/v1/campanhas/{criada['id']}").json()
    assert detalhe["metricas"]["total"] == 0


def test_optout_por_token_publico(client, db_session):
    decisor_id = _criar_decisor(client)
    criada = client.post(
        "/api/v1/campanhas",
        json={"nome": "Campanha", "tipo": "marketing", "canais": ["email"], "assunto": "A", "conteudo_email": "B"},
    ).json()
    destinatario = client.post(
        f"/api/v1/campanhas/{criada['id']}/destinatarios/decisores", json={"decisor_ids": [decisor_id]}
    ).json()[0]

    token = campanha_service.gerar_token_optout("tenant-teste", destinatario["id"])
    resposta = client.get(f"/api/v1/opt-out/campanha/{token}")

    assert resposta.status_code == 200
    assert resposta.json()["suprimido"] is True


def test_campanha_de_outro_tenant_nao_aparece(client, criar_usuario_autenticado):
    headers_outro_tenant = criar_usuario_autenticado("outro-tenant-campanha")
    client.post(
        "/api/v1/campanhas",
        json={"nome": "Minha", "tipo": "marketing", "canais": ["email"], "assunto": "A", "conteudo_email": "B"},
    )

    resposta = client.get("/api/v1/campanhas", headers=headers_outro_tenant)
    assert resposta.status_code == 200
    assert resposta.json() == []
