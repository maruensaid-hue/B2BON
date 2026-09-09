from app.models.tenant import Tenant


def test_busca_acha_conta_criada_via_api(client, criar_conta_com_decisor):
    criar_conta_com_decisor()  # a fixture sempre cria a conta como "Conta Teste"

    resposta = client.get("/api/v1/busca", params={"q": "Conta Teste"})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert any(item["tipo"] == "conta" and item["titulo"] == "Conta Teste" for item in corpo)


def test_busca_acha_negocio_e_traz_rota_do_crm(client, criar_conta_com_decisor):
    conta, decisor = criar_conta_com_decisor()
    negocio = client.post(
        "/api/v1/crm/negocios",
        json={"conta_id": conta.id, "decisor_id": decisor.id, "nome": "Oportunidade Buscável", "valor": 100.0},
    ).json()

    resposta = client.get("/api/v1/busca", params={"q": "Buscável"})

    corpo = resposta.json()
    item = next(i for i in corpo if i["tipo"] == "negocio")
    assert item["id"] == negocio["id"]
    assert item["rota"] == f"/crm?negocio_id={negocio['id']}"


def test_busca_acha_proposta_por_nome(client, criar_conta_com_decisor):
    conta, decisor = criar_conta_com_decisor()
    negocio = client.post(
        "/api/v1/crm/negocios",
        json={"conta_id": conta.id, "decisor_id": decisor.id, "nome": "Negócio", "valor": 100.0},
    ).json()
    client.post(
        f"/api/v1/crm/negocios/{negocio['id']}/propostas",
        files={"arquivo": ("proposta.pdf", b"%PDF-1.4", "application/pdf")},
        data={"nome": "Proposta Buscável Única"},
    )

    resposta = client.get("/api/v1/busca", params={"q": "Buscável Única"})

    corpo = resposta.json()
    assert any(item["tipo"] == "proposta" and item["titulo"] == "Proposta Buscável Única" for item in corpo)


def test_busca_super_admin_acha_tenant(client, db_session):
    db_session.add(Tenant(id="tenant-alvo-integracao", razao_social="Tenant Alvo Integração"))
    db_session.commit()

    resposta = client.get("/api/v1/busca", params={"q": "Alvo Integração"})

    corpo = resposta.json()
    assert any(item["tipo"] == "tenant" for item in corpo)


def test_busca_sem_autenticacao_recusa(client):
    resposta = client.get("/api/v1/busca", params={"q": "qualquercoisa"}, headers={"Authorization": ""})

    assert resposta.status_code == 401


def test_busca_termo_curto_devolve_lista_vazia(client):
    resposta = client.get("/api/v1/busca", params={"q": "a"})

    assert resposta.status_code == 200
    assert resposta.json() == []
