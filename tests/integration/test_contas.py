from app.models.conta import Conta
from app.providers.account_data.base import ContaCandidata, DecisorCandidato


def _candidato(cnpj: str, nome: str) -> ContaCandidata:
    return ContaCandidata(
        cnpj=cnpj,
        razao_social=nome,
        cnae_principal="6201500",
        porte="PEQUENO",
        uf="SP",
        situacao_cadastral="ATIVA",
        fonte="receita_federal_cnpj",
    )


def test_bloqueia_prospeccao_sem_icp_ativo(client, criar_icp):
    """E1-H1: sem ICP ativo, o motor não inicia prospecção (bloqueio explícito)."""
    icp = criar_icp()
    # desativa o ICP criando uma nova versão (a versão antiga deixa de estar ativa)
    client.put(
        f"/api/v1/icp/{icp['id']}",
        json={
            "nome": "ICP v2", "segmento": "Tecnologia", "porte": "PEQUENO", "regiao": "SP",
            "dores": [], "gatilhos": [], "cnae_codigos": ["6201500"], "ufs": ["SP"],
        },
    )

    resposta = client.post(f"/api/v1/icp/{icp['id']}/contas/gerar", json={"quantidade": 5})

    assert resposta.status_code == 409
    assert "ICP ativo" in resposta.json()["detalhe"]


def test_lista_gerada_tem_score_de_aderencia(client, criar_icp, fake_account_data):
    """E2-H1: geração de lista com score de aderência ao ICP por conta."""
    icp = criar_icp()
    fake_account_data.candidatos = [_candidato("11222333000191", "Alpha Tech")]

    resposta = client.post(f"/api/v1/icp/{icp['id']}/contas/gerar", json={"quantidade": 5})

    assert resposta.status_code == 201
    contas = resposta.json()["contas"]
    assert len(contas) == 1
    assert contas[0]["score_aderencia"] == 1.0  # CNAE + UF + porte batem


def test_dedupe_contra_contas_existentes(client, criar_icp, fake_account_data):
    """E2-H1: deduplicação contra contas já existentes."""
    icp = criar_icp()
    fake_account_data.candidatos = [_candidato("11222333000191", "Alpha Tech")]

    primeira = client.post(f"/api/v1/icp/{icp['id']}/contas/gerar", json={"quantidade": 5})
    segunda = client.post(f"/api/v1/icp/{icp['id']}/contas/gerar", json={"quantidade": 5})

    assert len(primeira.json()["contas"]) == 1
    assert len(segunda.json()["contas"]) == 0  # mesmo CNPJ não duplica


def test_geracao_nao_consome_franquia(client, criar_icp, fake_account_data):
    """E2-H1: gerar lista não consome franquia — só a ativação de cadência."""
    icp = criar_icp()
    fake_account_data.candidatos = [_candidato("11222333000191", "Alpha Tech")]

    client.post(f"/api/v1/icp/{icp['id']}/contas/gerar", json={"quantidade": 5})
    franquia = client.get("/api/v1/contas/franquia").json()

    assert franquia["usado"] == 0


def test_enriquecer_conta_registra_fonte_e_data(client, db_session, criar_icp, fake_account_data, fake_llm):
    """E2-H2: ficha de conta com campos enriquecidos e fonte/data de cada dado."""
    icp = criar_icp()
    fake_account_data.candidatos = [_candidato("11222333000191", "Alpha Tech")]
    conta_id = client.post(f"/api/v1/icp/{icp['id']}/contas/gerar", json={"quantidade": 5}).json()["contas"][0]["id"]

    conta = db_session.get(Conta, conta_id)
    conta.dominio = "alphatech.com.br"
    db_session.commit()

    fake_llm.definir_respostas(["porte: media\nsinal_publico: cresceu 20% ao ano"])
    resposta = client.post(f"/api/v1/contas/{conta_id}/enriquecer")

    assert resposta.status_code == 200
    campos = resposta.json()["campos"]
    assert len(campos) == 2
    for campo in campos:
        assert campo["fonte"] == "site_institucional"
        assert campo["coletado_em"]


def test_listar_contas_do_icp_sobrevive_a_refresh(client, criar_icp, fake_account_data):
    """Onda F2: a tela de Prospecção precisa reler as contas já geradas,
    não só a resposta pontual de gerar_lista."""
    icp = criar_icp()
    fake_account_data.candidatos = [_candidato("11222333000191", "Alpha Tech")]
    client.post(f"/api/v1/icp/{icp['id']}/contas/gerar", json={"quantidade": 5})

    resposta = client.get(f"/api/v1/icp/{icp['id']}/contas")

    assert resposta.status_code == 200
    contas = resposta.json()
    assert len(contas) == 1
    assert contas[0]["nome"] == "Alpha Tech"


def test_enriquecer_conta_via_brasilapi_registra_fonte(client, criar_icp, fake_account_data):
    """Onda E: enriquecimento pontual de uma conta via BrasilAPI, sem LLM."""
    icp = criar_icp()
    fake_account_data.candidatos = [_candidato("11222333000191", "Alpha Tech")]
    conta_id = client.post(f"/api/v1/icp/{icp['id']}/contas/gerar", json={"quantidade": 5}).json()["contas"][0]["id"]

    resposta = client.post(f"/api/v1/contas/{conta_id}/enriquecer-brasilapi")

    assert resposta.status_code == 200
    campos = resposta.json()["campos"]
    assert len(campos) >= 1
    for campo in campos:
        assert campo["fonte"] == "brasilapi_cnpj"
        assert campo["coletado_em"]


def test_mapear_decisores_com_cargo_e_canal(client, criar_icp, fake_account_data):
    """E2-H2: decisores mapeados com cargo e canal provável de contato."""
    icp = criar_icp()
    cnpj = "11222333000191"
    fake_account_data.candidatos = [_candidato(cnpj, "Alpha Tech")]
    fake_account_data.decisores = {cnpj: [DecisorCandidato(cnpj=cnpj, nome="Joao Silva", qualificacao="Sócio-Administrador")]}
    conta_id = client.post(f"/api/v1/icp/{icp['id']}/contas/gerar", json={"quantidade": 5}).json()["contas"][0]["id"]

    resposta = client.post(f"/api/v1/contas/{conta_id}/decisores/mapear")

    assert resposta.status_code == 200
    decisores = resposta.json()
    assert len(decisores) == 1
    assert decisores[0]["cargo"] == "Sócio-Administrador"
    assert decisores[0]["canal_provavel"] == "email"


def test_conta_e_decisor_persistidos_no_grafo(client, criar_icp, fake_account_data, fake_graph):
    """E2-H2: conta e decisores persistidos como nós/arestas no grafo (Neo4j)."""
    icp = criar_icp()
    cnpj = "11222333000191"
    fake_account_data.candidatos = [_candidato(cnpj, "Alpha Tech")]
    fake_account_data.decisores = {cnpj: [DecisorCandidato(cnpj=cnpj, nome="Joao Silva", qualificacao="Sócio")]}
    conta_id = client.post(f"/api/v1/icp/{icp['id']}/contas/gerar", json={"quantidade": 5}).json()["contas"][0]["id"]
    client.post(f"/api/v1/contas/{conta_id}/decisores/mapear")

    assert f"conta:{conta_id}" in fake_graph.nos
    arestas_decisor_de = [a for a in fake_graph.arestas if a["tipo"] == "DECISOR_DE"]
    assert len(arestas_decisor_de) == 1
    assert arestas_decisor_de[0]["destino"] == f"conta:{conta_id}"


def test_grafo_navegavel_por_conta(client, criar_icp, fake_account_data):
    """E2-H3: visualização navegável do grafo por conta."""
    icp = criar_icp()
    cnpj = "11222333000191"
    fake_account_data.candidatos = [_candidato(cnpj, "Alpha Tech")]
    fake_account_data.decisores = {cnpj: [DecisorCandidato(cnpj=cnpj, nome="Joao Silva", qualificacao="Sócio")]}
    conta_id = client.post(f"/api/v1/icp/{icp['id']}/contas/gerar", json={"quantidade": 5}).json()["contas"][0]["id"]
    client.post(f"/api/v1/contas/{conta_id}/decisores/mapear")

    resposta = client.get(f"/api/v1/contas/{conta_id}/grafo")

    assert resposta.status_code == 200
    grafo = resposta.json()
    tipos = {no["tipo"] for no in grafo["nos"]}
    assert tipos == {"Conta", "Decisor"}


def test_interacao_aparece_ligada_ao_decisor(client, criar_icp, fake_account_data, fake_graph):
    """E2-H3: interações de cadência aparecem como eventos ligados ao decisor."""
    icp = criar_icp()
    cnpj = "11222333000191"
    fake_account_data.candidatos = [_candidato(cnpj, "Alpha Tech")]
    fake_account_data.decisores = {cnpj: [DecisorCandidato(cnpj=cnpj, nome="Joao Silva", qualificacao="Sócio")]}
    conta_id = client.post(f"/api/v1/icp/{icp['id']}/contas/gerar", json={"quantidade": 5}).json()["contas"][0]["id"]
    decisor_id = client.post(f"/api/v1/contas/{conta_id}/decisores/mapear").json()[0]["id"]

    # Interações de cadência são do E3 (Onda 2); aqui simulamos o evento no
    # grafo diretamente para provar que a leitura do grafo já sabe exibi-lo.
    fake_graph.registrar_interacao("tenant-teste", decisor_id, 1, {"tipo_evento": "email_enviado"})

    grafo = client.get(f"/api/v1/contas/{conta_id}/grafo").json()

    interacoes = [no for no in grafo["nos"] if no["tipo"] == "Interacao"]
    assert len(interacoes) == 1
    arestas_interacao = [a for a in grafo["arestas"] if a["tipo"] == "INTERAGIU_COM"]
    assert arestas_interacao[0]["origem"] == f"decisor:{decisor_id}"


def test_export_pdf_gera_arquivo_valido(client, criar_icp, fake_account_data):
    """E2-H3: exportação da ficha da conta em PDF."""
    icp = criar_icp()
    fake_account_data.candidatos = [_candidato("11222333000191", "Alpha Tech")]
    conta_id = client.post(f"/api/v1/icp/{icp['id']}/contas/gerar", json={"quantidade": 5}).json()["contas"][0]["id"]

    resposta = client.get(f"/api/v1/contas/{conta_id}/export/pdf")

    assert resposta.status_code == 200
    assert resposta.headers["content-type"] == "application/pdf"
    assert resposta.content.startswith(b"%PDF")
