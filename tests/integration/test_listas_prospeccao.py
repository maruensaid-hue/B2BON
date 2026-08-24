TENANT_ID = "tenant-teste"


def test_criar_lista_sem_icp(client):
    resposta = client.post("/api/v1/listas-prospeccao", json={"nome": "Evento Febraban 2026"})

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["nome"] == "Evento Febraban 2026"
    assert corpo["icp_id"] is None
    assert corpo["cargos_alvo"] is None


def test_criar_lista_com_cargos_alvo_e_icp(client, criar_icp):
    icp = criar_icp()

    resposta = client.post(
        "/api/v1/listas-prospeccao",
        json={"nome": "Security Leaders 2026", "icp_id": icp["id"], "cargos_alvo": ["CISO", "Diretor de Segurança da Informação"]},
    )

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["icp_id"] == icp["id"]
    assert corpo["cargos_alvo"] == ["CISO", "Diretor de Segurança da Informação"]


def test_criar_lista_com_icp_inexistente_falha(client):
    resposta = client.post("/api/v1/listas-prospeccao", json={"nome": "Lista X", "icp_id": 999999})
    assert resposta.status_code == 404


def test_listar_listas(client):
    client.post("/api/v1/listas-prospeccao", json={"nome": "Lista A"})
    client.post("/api/v1/listas-prospeccao", json={"nome": "Lista B"})

    resposta = client.get("/api/v1/listas-prospeccao")

    assert resposta.status_code == 200
    nomes = {lista["nome"] for lista in resposta.json()}
    assert nomes == {"Lista A", "Lista B"}


def test_importar_participantes_cria_contas_e_decisores(client):
    lista = client.post("/api/v1/listas-prospeccao", json={"nome": "Evento Febraban 2026"}).json()

    resposta = client.post(
        f"/api/v1/listas-prospeccao/{lista['id']}/contas/importar-participantes",
        json={
            "participantes": [
                {"nome": "Joana Silva", "empresa": "Clinica Vida Plena", "cargo": "Diretora", "email": "joana@vidaplena.com"},
                {"nome": "Marcos Souza", "empresa": "Clinica Vida Plena", "cargo": "Sócio"},
                {"nome": "Ana Paula", "empresa": "Studio Beleza Ltda"},
            ]
        },
    )

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["contas_criadas"] == 2
    assert corpo["contas_reaproveitadas"] == 0
    assert corpo["decisores_criados"] == 3
    assert all(conta["icp_id"] is None for conta in corpo["contas"])


def test_importar_participantes_em_lista_com_icp_herda_icp_id(client, criar_icp):
    icp = criar_icp()
    lista = client.post("/api/v1/listas-prospeccao", json={"nome": "Security Leaders 2026", "icp_id": icp["id"]}).json()

    resposta = client.post(
        f"/api/v1/listas-prospeccao/{lista['id']}/contas/importar-participantes",
        json={"participantes": [{"nome": "Joana Silva", "empresa": "Alpha Tech"}]},
    )

    assert resposta.json()["contas"][0]["icp_id"] == icp["id"]


def test_importar_participantes_lista_inexistente_e_404(client):
    resposta = client.post(
        "/api/v1/listas-prospeccao/999999/contas/importar-participantes",
        json={"participantes": [{"nome": "Joana Silva", "empresa": "Alpha Tech"}]},
    )
    assert resposta.status_code == 404


def test_importar_participantes_enfileira_so_contas_novas_para_enriquecimento(client):
    """Empresa já existente (reaproveitada) não entra de novo na fila —
    presumivelmente já foi enriquecida antes."""
    lista = client.post("/api/v1/listas-prospeccao", json={"nome": "Evento Febraban 2026"}).json()
    client.post("/api/v1/leads/contas", json={"nome": "Clinica Vida Plena"})

    resposta = client.post(
        f"/api/v1/listas-prospeccao/{lista['id']}/contas/importar-participantes",
        json={
            "participantes": [
                {"nome": "Joana Silva", "empresa": "Clinica Vida Plena"},
                {"nome": "Ana Paula", "empresa": "Studio Beleza Ltda"},
            ]
        },
    )

    corpo = resposta.json()
    assert corpo["contas_criadas"] == 1
    assert corpo["contas_reaproveitadas"] == 1
    assert corpo["contas_enfileiradas_para_enriquecimento"] == 1


def test_importar_participantes_acumula_observacoes_na_conta(client):
    """Pedido do usuário: coluna extra da planilha mapeada pra
    "Observações" entra como parte do enriquecimento de dados da empresa
    (não do decisor) — acumulando se mais de um participante trouxer
    informação diferente sobre a mesma empresa."""
    lista = client.post("/api/v1/listas-prospeccao", json={"nome": "Evento Febraban 2026"}).json()

    resposta = client.post(
        f"/api/v1/listas-prospeccao/{lista['id']}/contas/importar-participantes",
        json={
            "participantes": [
                {"nome": "Joana Silva", "empresa": "Alpha Tech", "observacoes": "Interessada em projeto de nuvem"},
                {"nome": "Marcos Souza", "empresa": "Alpha Tech", "observacoes": "Já usa concorrente X"},
            ]
        },
    )

    conta = resposta.json()["contas"][0]
    assert "Interessada em projeto de nuvem" in conta["observacoes"]
    assert "Já usa concorrente X" in conta["observacoes"]


def test_listar_contas_de_uma_lista(client):
    lista1 = client.post("/api/v1/listas-prospeccao", json={"nome": "Lista 1"}).json()
    lista2 = client.post("/api/v1/listas-prospeccao", json={"nome": "Lista 2"}).json()
    client.post(
        f"/api/v1/listas-prospeccao/{lista1['id']}/contas/importar-participantes",
        json={"participantes": [{"nome": "Joana Silva", "empresa": "Alpha Tech"}]},
    )
    client.post(
        f"/api/v1/listas-prospeccao/{lista2['id']}/contas/importar-participantes",
        json={"participantes": [{"nome": "Marcos Souza", "empresa": "Beta Corp"}]},
    )

    contas_lista1 = client.get(f"/api/v1/listas-prospeccao/{lista1['id']}/contas").json()

    assert len(contas_lista1) == 1
    assert contas_lista1[0]["nome"] == "Alpha Tech"


def test_mapear_decisores_de_conta_em_lista_com_cargos_alvo_restringe_busca(client, fake_contact_enrichment):
    """O coração do pedido: lista com cargos_alvo definido restringe a
    busca do provedor de enriquecimento na requisição em si (economiza
    consulta), em vez de filtrar depois de já ter revelado o contato."""
    lista = client.post(
        "/api/v1/listas-prospeccao",
        json={"nome": "Security Leaders 2026", "cargos_alvo": ["CISO", "Diretor de Segurança da Informação"]},
    ).json()
    importado = client.post(
        f"/api/v1/listas-prospeccao/{lista['id']}/contas/importar-participantes",
        json={"participantes": [{"nome": "Joana Silva", "empresa": "Alpha Tech"}]},
    ).json()
    conta_id = importado["contas"][0]["id"]

    client.post(f"/api/v1/contas/{conta_id}/decisores/mapear")

    assert len(fake_contact_enrichment.buscas) == 1
    assert fake_contact_enrichment.buscas[0].cargos_alvo == ["CISO", "Diretor de Segurança da Informação"]


def test_mapear_decisores_de_conta_sem_lista_usa_default_generico(client, fake_contact_enrichment, criar_icp):
    """Conta fora de qualquer lista (ou de lista sem cargos_alvo) continua
    com o comportamento de hoje — sem regressão."""
    icp = criar_icp()
    conta = client.post(f"/api/v1/icp/{icp['id']}/contas", json={"nome": "Alpha Tech"}).json()

    client.post(f"/api/v1/contas/{conta['id']}/decisores/mapear")

    from app.providers.contact_enrichment.base import SENIORIDADE_ALVO

    assert fake_contact_enrichment.buscas[0].cargos_alvo == SENIORIDADE_ALVO
