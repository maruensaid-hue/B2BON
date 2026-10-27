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


def test_marcar_pronta_comeca_o_envio_logo_em_seguida(client, db_session, fake_email, fake_whatsapp, monkeypatch):
    """O envio não espera o agendador externo: ao marcar como pronta, a campanha sai em segundo plano."""

    from app.api.deps import get_sessao_factory
    from app.api.v1 import campanhas as rota
    from app.main import app
    from app.models.tenant import Tenant
    from tests.conftest import TENANT_ID

    if db_session.get(Tenant, TENANT_ID) is None:
        db_session.add(Tenant(id=TENANT_ID, razao_social="Tenant de teste"))
        db_session.commit()
    monkeypatch.setattr(rota, "resolver_email_provider", lambda tenant_id, db: fake_email)
    monkeypatch.setattr(rota, "resolver_whatsapp_provider", lambda tenant_id, db: fake_whatsapp)
    monkeypatch.setattr(db_session, "close", lambda: None)  # a "sessão própria" da tarefa é a mesma dos testes
    app.dependency_overrides[get_sessao_factory] = lambda: (lambda: db_session)

    decisor_id = _criar_decisor(client)
    criada = client.post(
        "/api/v1/campanhas",
        json={"nome": "Imediata", "tipo": "marketing", "canais": ["email"], "assunto": "Assunto", "conteudo_email": "Corpo"},
    ).json()
    client.post(f"/api/v1/campanhas/{criada['id']}/destinatarios/decisores", json={"decisor_ids": [decisor_id]})

    pronta = client.post(f"/api/v1/campanhas/{criada['id']}/marcar-pronta")

    assert pronta.status_code == 200 and pronta.json()["status"] == "pronta"
    assert [e["destinatario"] for e in fake_email.envios] == ["fulano@teste.com"]
    detalhe = client.get(f"/api/v1/campanhas/{criada['id']}").json()
    assert detalhe["status"] == "concluida" and detalhe["metricas"]["enviado"] == 1


def test_voltar_para_rascunho_pela_api_permite_editar_o_conteudo(client):
    decisor_id = _criar_decisor(client)
    criada = client.post(
        "/api/v1/campanhas",
        json={"nome": "Editavel", "tipo": "marketing", "canais": ["email"], "assunto": "Antigo", "conteudo_email": "Corpo antigo"},
    ).json()
    client.post(f"/api/v1/campanhas/{criada['id']}/destinatarios/decisores", json={"decisor_ids": [decisor_id]})
    client.post(f"/api/v1/campanhas/{criada['id']}/marcar-pronta")
    bloqueada = client.put(
        f"/api/v1/campanhas/{criada['id']}",
        json={"nome": "Editavel", "tipo": "marketing", "canais": ["email"], "assunto": "Novo", "conteudo_email": "Corpo novo"},
    )
    assert bloqueada.status_code in (400, 409, 422)  # pronta: só edita depois de voltar ao rascunho

    voltou = client.post(f"/api/v1/campanhas/{criada['id']}/voltar-para-rascunho")
    assert voltou.status_code == 200 and voltou.json()["status"] == "rascunho"

    editada = client.put(
        f"/api/v1/campanhas/{criada['id']}",
        json={"nome": "Editavel", "tipo": "marketing", "canais": ["email"], "assunto": "Novo", "conteudo_email": "Corpo novo"},
    )
    assert editada.status_code == 200
    assert editada.json()["assunto"] == "Novo" and editada.json()["conteudo_email"] == "Corpo novo"


def test_marcar_pronta_so_para_os_selecionados_pela_api(client, db_session, fake_email, fake_whatsapp):
    from tests.conftest import TENANT_ID

    criada = client.post(
        "/api/v1/campanhas",
        json={"nome": "Teste parcial", "tipo": "marketing", "canais": ["email"], "assunto": "Assunto", "conteudo_email": "Corpo"},
    ).json()
    client.post(
        f"/api/v1/campanhas/{criada['id']}/destinatarios/avulsos",
        json={"destinatarios": [{"nome": f"Pessoa {i}", "email": f"pessoa{i}@teste.com"} for i in range(3)]},
    )
    ids = [d["id"] for d in client.get(f"/api/v1/campanhas/{criada['id']}").json()["destinatarios"]]

    vazia = client.post(f"/api/v1/campanhas/{criada['id']}/marcar-pronta", json={"destinatario_ids": []})
    assert vazia.status_code == 422

    pronta = client.post(f"/api/v1/campanhas/{criada['id']}/marcar-pronta", json={"destinatario_ids": [ids[1]]})
    assert pronta.status_code == 200 and pronta.json()["status"] == "pronta"
    metricas = client.get(f"/api/v1/campanhas/{criada['id']}").json()["metricas"]
    assert metricas["pendente"] == 1 and metricas["retido"] == 2

    campanha_service.processar_pendentes(db_session, TENANT_ID, fake_email, fake_whatsapp)

    assert [e["destinatario"] for e in fake_email.envios] == ["pessoa1@teste.com"]
    detalhe = client.get(f"/api/v1/campanhas/{criada['id']}").json()
    assert detalhe["status"] == "rascunho"
    assert detalhe["metricas"]["enviado"] == 1 and detalhe["metricas"]["pendente"] == 2


def test_previa_da_campanha_pela_api(client):
    criada = client.post(
        "/api/v1/campanhas",
        json={"nome": "Previa", "tipo": "marketing", "canais": ["email"], "assunto": "Oi [Nome]", "conteudo_email": "Olá, [Nome],\nA [Empresa]."},
    ).json()
    client.post(
        f"/api/v1/campanhas/{criada['id']}/destinatarios/avulsos",
        json={"destinatarios": [{"nome": "Maria da Silva", "email": "maria@teste.com"}]},
    )

    resposta = client.get(f"/api/v1/campanhas/{criada['id']}/previa")

    assert resposta.status_code == 200
    assert resposta.json() == {"destinatario_nome": "Maria da Silva", "assunto": "Oi Maria", "corpo": "Olá, Maria,\nA a sua empresa."}
    assert client.get("/api/v1/campanhas/999999/previa").status_code == 404
