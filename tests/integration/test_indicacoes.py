from app.providers.account_data.base import ContaCandidata

TENANT_ID = "tenant-teste"


def _obter_token_da_pesquisa(fake_whatsapp) -> str:
    texto = fake_whatsapp.envios[-1]["texto"]
    return texto.rsplit(" ", 1)[-1]


def _tornar_promotor(client, decisor_id: int, fake_whatsapp, fake_llm, nota: int = 10) -> dict:
    fake_llm.definir_respostas(["Mensagem de indicação com o código pronta para envio."])
    client.post(f"/api/v1/decisores/{decisor_id}/marco-entrega")
    token = _obter_token_da_pesquisa(fake_whatsapp)
    return client.post(f"/api/v1/nps/responder/{token}", json={"nota": nota}).json()


def test_indicacao_so_solicitada_para_promotor(client, criar_conta_com_decisor, fake_whatsapp, fake_llm):
    """E11-H2: pedido de indicação disparado apenas para promotores (NPS >= 9)."""
    conta, decisor = criar_conta_com_decisor()
    client.post(f"/api/v1/decisores/{decisor.id}/marco-entrega")
    token = _obter_token_da_pesquisa(fake_whatsapp)

    client.post(f"/api/v1/nps/responder/{token}", json={"nota": 7})  # neutro

    assert client.get("/api/v1/indicacoes").json() == []


def test_indicacao_solicitada_para_promotor(client, criar_conta_com_decisor, fake_whatsapp, fake_llm):
    conta, decisor = criar_conta_com_decisor()
    _tornar_promotor(client, decisor.id, fake_whatsapp, fake_llm)

    indicacoes = client.get("/api/v1/indicacoes").json()

    assert len(indicacoes) == 1
    assert indicacoes[0]["status"] == "aguardando"
    assert indicacoes[0]["promotor_decisor_id"] == decisor.id


def test_mensagem_de_indicacao_passa_pela_fila_de_aprovacoes(client, criar_conta_com_decisor, fake_whatsapp, fake_llm):
    """E11-H2: mensagem gerada pelo motor e submetida à fila de aprovações (E4) antes do envio."""
    conta, decisor = criar_conta_com_decisor()
    _tornar_promotor(client, decisor.id, fake_whatsapp, fake_llm)

    fila = client.get("/api/v1/aprovacoes").json()
    item_indicacao = next(i for i in fila if i["cadencia_id"] is None)

    assert item_indicacao["status"] == "pendente"
    assert item_indicacao["decisor_id"] == decisor.id


def test_codigo_indicacao_rastreavel_ponta_a_ponta(client, criar_conta_com_decisor, fake_whatsapp, fake_llm):
    """E11-H2: link/código de indicação rastreável de ponta a ponta — o
    código é embutido no prompt que gera a mensagem enviada ao promotor."""
    conta, decisor = criar_conta_com_decisor()
    _tornar_promotor(client, decisor.id, fake_whatsapp, fake_llm)

    indicacao = client.get("/api/v1/indicacoes").json()[0]
    codigo = indicacao["codigo_indicacao"]

    assert codigo.startswith("IND-")
    assert any(codigo in chamada.prompt for chamada in fake_llm.chamadas)


def _gerar_conta(client, icp_id: int, fake_account_data, cnpj: str) -> dict:
    fake_account_data.candidatos = [
        ContaCandidata(
            cnpj=cnpj, razao_social="Indicado Ltda", cnae_principal="6201500", porte="PEQUENO", uf="SP",
            situacao_cadastral="ATIVA",
        )
    ]
    return client.post(f"/api/v1/icp/{icp_id}/contas/gerar", json={"quantidade": 5}).json()["contas"][0]


def test_converter_indicacao_grava_aresta_no_grafo(
    client, criar_conta_com_decisor, fake_whatsapp, fake_llm, fake_graph, criar_icp, fake_account_data
):
    """E11-H3: indicação registrada como aresta no grafo, ligando promotor e indicado."""
    conta, decisor = criar_conta_com_decisor()
    _tornar_promotor(client, decisor.id, fake_whatsapp, fake_llm)
    codigo = client.get("/api/v1/indicacoes").json()[0]["codigo_indicacao"]

    icp = criar_icp()
    conta_indicada = _gerar_conta(client, icp["id"], fake_account_data, "99888777000166")

    resposta = client.post(f"/api/v1/indicacoes/{codigo}/converter", json={"conta_id": conta_indicada["id"]})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["status"] == "convertida"
    assert corpo["conta_gerada_id"] == conta_indicada["id"]

    arestas_indicou = [a for a in fake_graph.arestas if a["tipo"] == "INDICOU"]
    assert len(arestas_indicou) == 1
    assert arestas_indicou[0]["origem"] == f"decisor:{decisor.id}"
    assert arestas_indicou[0]["destino"] == f"conta:{conta_indicada['id']}"


def test_indicacao_intra_rede_identificada(
    client, criar_conta_com_decisor, fake_whatsapp, fake_llm, criar_icp, fake_account_data, fake_rede_social, db_session
):
    """E11-H3: indicações intra-rede identificadas como tal."""
    conta, decisor = criar_conta_com_decisor()
    _tornar_promotor(client, decisor.id, fake_whatsapp, fake_llm)
    codigo = client.get("/api/v1/indicacoes").json()[0]["codigo_indicacao"]

    icp = criar_icp()
    conta_indicada = _gerar_conta(client, icp["id"], fake_account_data, "99888777000166")
    decisor_indicado = client.post(
        f"/api/v1/contas/{conta_indicada['id']}/decisores",
        json={"nome": "Decisor Indicado", "email": "indicado@empresateste.com.br"},
    ).json()
    fake_rede_social.assinantes.add(decisor_indicado["email"])

    resposta = client.post(f"/api/v1/indicacoes/{codigo}/converter", json={"conta_id": conta_indicada["id"]})

    assert resposta.json()["intra_rede"] is True


def test_conversao_dobrada_nao_e_permitida(client, criar_conta_com_decisor, fake_whatsapp, fake_llm, criar_icp, fake_account_data):
    conta, decisor = criar_conta_com_decisor()
    _tornar_promotor(client, decisor.id, fake_whatsapp, fake_llm)
    codigo = client.get("/api/v1/indicacoes").json()[0]["codigo_indicacao"]
    icp = criar_icp()
    conta_indicada = _gerar_conta(client, icp["id"], fake_account_data, "99888777000166")
    client.post(f"/api/v1/indicacoes/{codigo}/converter", json={"conta_id": conta_indicada["id"]})

    resposta = client.post(f"/api/v1/indicacoes/{codigo}/converter", json={"conta_id": conta_indicada["id"]})

    assert resposta.status_code == 409


def test_oportunidade_vinculada_automaticamente_ao_confirmar_reuniao(
    client, criar_conta_com_decisor, fake_whatsapp, fake_llm, fake_graph, criar_icp, fake_account_data
):
    """E11-H3: aresta promotor->indicado->oportunidade completada automaticamente
    quando a reunião do indicado é confirmada — sem ação manual duplicada."""
    conta, decisor = criar_conta_com_decisor()
    _tornar_promotor(client, decisor.id, fake_whatsapp, fake_llm)
    codigo = client.get("/api/v1/indicacoes").json()[0]["codigo_indicacao"]

    icp = criar_icp()
    conta_indicada = _gerar_conta(client, icp["id"], fake_account_data, "99888777000166")
    decisor_indicado = client.post(
        f"/api/v1/contas/{conta_indicada['id']}/decisores",
        json={"nome": "Decisor Indicado", "email": "indicado@empresateste.com.br", "telefone": "+5511977776666"},
    ).json()
    client.post(f"/api/v1/indicacoes/{codigo}/converter", json={"conta_id": conta_indicada["id"]})

    proposta = client.post(
        f"/api/v1/decisores/{decisor_indicado['id']}/reunioes/propor", json={"vendedor_id": "vendedor-1"}
    ).json()
    horario = proposta["horarios_propostos"][0]
    confirmada = client.post(
        f"/api/v1/reunioes/{proposta['id']}/confirmar", json={"horario_escolhido": horario}
    ).json()

    arestas_oportunidade = [a for a in fake_graph.arestas if a["tipo"] == "GEROU_OPORTUNIDADE"]
    assert len(arestas_oportunidade) == 1
    assert arestas_oportunidade[0]["origem"] == f"conta:{conta_indicada['id']}"

    eventos = {e["evento_tipo"] for e in client.get("/api/v1/auditoria").json()}
    assert "indicacao_vinculada_a_oportunidade" in eventos
    assert confirmada["origem_crm_id"] is not None


def test_painel_indicadores_mostra_origem_indicacao_apos_conversao(
    client, criar_conta_com_decisor, fake_whatsapp, fake_llm, criar_icp, fake_account_data
):
    """Continuidade com a Onda 4: `panel_service.origem_oportunidade` já lê
    `Conta.origem == "indicacao"` sem qualquer alteração nesta onda."""
    conta, decisor = criar_conta_com_decisor()
    _tornar_promotor(client, decisor.id, fake_whatsapp, fake_llm)
    codigo = client.get("/api/v1/indicacoes").json()[0]["codigo_indicacao"]

    icp = criar_icp()
    conta_indicada = _gerar_conta(client, icp["id"], fake_account_data, "99888777000166")
    client.post(f"/api/v1/indicacoes/{codigo}/converter", json={"conta_id": conta_indicada["id"]})

    indicadores = client.get(
        "/api/v1/painel/indicadores", params={"data_inicio": "2020-01-01", "data_fim": "2030-01-01"}
    ).json()

    assert indicadores["energia"]["origem_oportunidade"]["indicacao"] == 1
