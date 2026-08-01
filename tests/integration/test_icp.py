def test_criar_icp_retorna_versionado_e_ativo(client, criar_icp):
    icp = criar_icp()

    assert icp["versao"] == 1
    assert icp["ativo"] is True
    assert icp["grupo_id"]


def test_icp_versionado_preserva_historico(client, criar_icp):
    """E1-H1: ICP salvo como entidade versionada, editável a qualquer momento."""
    icp = criar_icp()

    resposta = client.put(
        f"/api/v1/icp/{icp['id']}",
        json={
            "nome": "ICP Teste v2",
            "segmento": "Tecnologia",
            "porte": "PEQUENO",
            "regiao": "SP",
            "dores": ["nova dor"],
            "gatilhos": [],
            "cnae_codigos": ["6201500"],
            "ufs": ["SP"],
        },
    )
    assert resposta.status_code == 200
    nova_versao = resposta.json()
    assert nova_versao["versao"] == 2
    assert nova_versao["grupo_id"] == icp["grupo_id"]

    historico = client.get(f"/api/v1/icp/grupo/{icp['grupo_id']}").json()
    assert [v["versao"] for v in historico] == [1, 2]
    assert historico[0]["ativo"] is False  # versão antiga preservada, mas desativada
    assert historico[1]["ativo"] is True


def test_clonagem_preserva_configuracao_original(client, criar_icp):
    """E1-H4: clonagem em 1 clique, sem perder a configuração original."""
    icp = criar_icp()

    resposta = client.post(f"/api/v1/icp/{icp['id']}/clonar")

    assert resposta.status_code == 201
    clone = resposta.json()
    assert clone["id"] != icp["id"]
    assert clone["grupo_id"] != icp["grupo_id"]  # linhagem independente
    assert clone["segmento"] == icp["segmento"]
    assert clone["cnae_codigos"] == icp["cnae_codigos"]

    original_ainda_existe = client.get(f"/api/v1/icp/{icp['id']}")
    assert original_ainda_existe.status_code == 200
    assert original_ainda_existe.json()["ativo"] is True


def test_performance_compara_icps_ativos(client, criar_icp):
    """E1-H4: comparativo simples de performance entre ICPs ativos."""
    icp_a = criar_icp(nome="ICP A")
    criar_icp(nome="ICP B", cnae_codigos=["4711301"], ufs=["RJ"])

    resposta = client.get("/api/v1/icp/performance")

    assert resposta.status_code == 200
    itens = {item["icp_id"]: item for item in resposta.json()}
    assert icp_a["id"] in itens
    assert itens[icp_a["id"]]["total_contas"] == 0
    assert itens[icp_a["id"]]["score_medio"] is None
