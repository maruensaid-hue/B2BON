import unicodedata

from app.models.conta import Conta
from app.models.estagio_funil import EstagioFunil
from app.models.negocio import Negocio
from app.models.usuario import Usuario
from app.providers.account_data.base import ContaCandidata, DecisorCandidato
from app.providers.contact_enrichment.base import ContatoCandidato

TENANT_ID = "tenant-teste"


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


def test_enriquecer_em_lote_enfileira_as_contas_selecionadas(client, db_session, criar_icp, fake_account_data):
    """Botão "Enriquecer selecionadas" na tela de Prospecção: enfileira as
    contas escolhidas na mesma fila usada pela importação de planilha,
    sem enriquecer na hora (evita timeout de proxy com várias contas)."""
    from app.models.fila_enriquecimento_conta import FilaEnriquecimentoConta

    icp = criar_icp()
    fake_account_data.candidatos = [
        _candidato("11222333000191", "Alpha Tech"),
        _candidato("22333444000192", "Beta Tech"),
    ]
    contas = client.post(f"/api/v1/icp/{icp['id']}/contas/gerar", json={"quantidade": 5}).json()["contas"]

    resposta = client.post(
        "/api/v1/contas/enriquecer-em-lote", json={"conta_ids": [conta["id"] for conta in contas]}
    )

    assert resposta.status_code == 200
    assert resposta.json() == {"contas_enfileiradas": 2}
    itens = db_session.query(FilaEnriquecimentoConta).all()
    assert {item.conta_id for item in itens} == {conta["id"] for conta in contas}
    assert all(item.status == "pendente" for item in itens)


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
    # 1 "pagina_pesquisada" (do marcador === url === do site_fetcher) + 2 campos da IA
    assert len(campos) == 3
    for campo in campos:
        assert campo["fonte"] == "pesquisa_no_site"
        assert campo["coletado_em"]
    assert any(campo["campo"] == "pagina_pesquisada" for campo in campos)


def test_enriquecer_sem_dominio_descobre_e_persiste(client, fake_llm, fake_web_search):
    """Pedido do usuário: enriquecimento de site deve descobrir o domínio
    sozinho quando a conta ainda não tem um cadastrado, e salvar na ficha."""
    from app.providers.web_search.base import ResultadoBusca

    conta_id = client.post("/api/v1/leads/contas", json={"nome": "Beta Clinica Descoberta"}).json()["id"]
    fake_web_search.resultados = [ResultadoBusca(titulo="Beta Clinica", url="https://betaclinica.com.br", descricao="")]
    fake_llm.definir_respostas(["porte: pequena"])

    resposta = client.post(f"/api/v1/contas/{conta_id}/enriquecer")

    assert resposta.status_code == 200
    campos_por_nome = {campo["campo"]: campo["valor"] for campo in resposta.json()["campos"]}
    assert campos_por_nome["dominio_descoberto_automaticamente"] == "betaclinica.com.br"

    conta_atualizada = client.get(f"/api/v1/contas/{conta_id}").json()
    assert conta_atualizada["dominio"] == "betaclinica.com.br"


def test_enriquecer_sem_dominio_e_sem_busca_bem_sucedida_falha_com_mensagem_clara(client, fake_web_search):
    conta_id = client.post("/api/v1/leads/contas", json={"nome": "Empresa Sem Site Localizavel"}).json()["id"]

    resposta = client.post(f"/api/v1/contas/{conta_id}/enriquecer")

    assert resposta.status_code == 409
    assert "descobrir automaticamente" in resposta.json()["detalhe"]


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


def test_listar_todas_as_contas_inclui_leads_sem_icp(client, criar_icp, fake_account_data):
    """O seletor "conta existente" do Kanban precisa enxergar tanto contas
    de um ICP quanto leads (sem ICP) — antes só listava por ICP e não
    havia como escolher um lead pra criar um negócio nele."""
    icp = criar_icp()
    fake_account_data.candidatos = [_candidato("11222333000191", "Alpha Tech")]
    client.post(f"/api/v1/icp/{icp['id']}/contas/gerar", json={"quantidade": 5})
    client.post("/api/v1/leads/contas", json={"nome": "Lead Sem ICP"})

    resposta = client.get("/api/v1/contas")

    assert resposta.status_code == 200
    nomes = {conta["nome"] for conta in resposta.json()}
    assert "Alpha Tech" in nomes
    assert "Lead Sem ICP" in nomes


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


def test_criar_conta_manual_via_crm(client, criar_icp):
    """Bug reportado: o Kanban só deixava referenciar uma conta já
    existente por ID cru — precisa dar pra cadastrar o cliente na hora."""
    icp = criar_icp()

    resposta = client.post(
        f"/api/v1/icp/{icp['id']}/contas",
        json={"nome": "Clínica Indicação Direta", "cnpj": None, "dominio": "clinicaindicacao.com.br"},
    )

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["nome"] == "Clínica Indicação Direta"
    assert corpo["origem"] == "manual"
    assert corpo["status"] == "prospectada"


def test_atualizar_conta_nome_fantasia_e_dominio(client, criar_icp, fake_account_data):
    """Bug reportado: a Receita Federal não traz site, e a razão social nem
    sempre é a marca comercial conhecida — precisa dar pra editar os dois."""
    icp = criar_icp()
    fake_account_data.candidatos = [_candidato("11222333000191", "Alpha Tech Consultoria Ltda")]
    conta_id = client.post(f"/api/v1/icp/{icp['id']}/contas/gerar", json={"quantidade": 5}).json()["contas"][0]["id"]

    resposta = client.put(
        f"/api/v1/contas/{conta_id}",
        json={"nome": "Alpha Tech Consultoria Ltda", "nome_fantasia": "Alpha Tech", "dominio": "alphatech.com.br"},
    )

    assert resposta.status_code == 200
    assert resposta.json()["nome_fantasia"] == "Alpha Tech"
    assert resposta.json()["dominio"] == "alphatech.com.br"


def test_atualizar_conta_normaliza_dominio_com_protocolo(client, criar_icp, fake_account_data):
    """Bug real de produção: colar a URL completa (com https://) fazia
    site_fetcher montar "https://https://..." e quebrar com erro de DNS."""
    icp = criar_icp()
    fake_account_data.candidatos = [_candidato("22333444000155", "Beta Clinica")]
    conta_id = client.post(f"/api/v1/icp/{icp['id']}/contas/gerar", json={"quantidade": 5}).json()["contas"][0]["id"]

    casos = [
        ("https://www.betaclinica.com.br", "www.betaclinica.com.br"),
        ("http://betaclinica.com.br/", "betaclinica.com.br"),
        ("  betaclinica.com.br  ", "betaclinica.com.br"),
    ]
    for entrada, esperado in casos:
        resposta = client.put(f"/api/v1/contas/{conta_id}", json={"nome": "Beta Clinica", "dominio": entrada})
        assert resposta.status_code == 200
        assert resposta.json()["dominio"] == esperado


def test_atualizar_decisor(client, criar_icp, fake_account_data):
    icp = criar_icp()
    cnpj = "11222333000191"
    fake_account_data.candidatos = [_candidato(cnpj, "Alpha Tech")]
    fake_account_data.decisores = {cnpj: [DecisorCandidato(cnpj=cnpj, nome="Joao Silva", qualificacao="Sócio")]}
    conta_id = client.post(f"/api/v1/icp/{icp['id']}/contas/gerar", json={"quantidade": 5}).json()["contas"][0]["id"]
    decisor_id = client.post(f"/api/v1/contas/{conta_id}/decisores/mapear").json()[0]["id"]

    resposta = client.put(
        f"/api/v1/contas/{conta_id}/decisores/{decisor_id}",
        json={"nome": "João Silva", "email": "joao@alphatech.com.br", "telefone": "11999998888"},
    )

    assert resposta.status_code == 200
    assert resposta.json()["email"] == "joao@alphatech.com.br"
    assert resposta.json()["telefone"] == "11999998888"

    listados = client.get(f"/api/v1/contas/{conta_id}/decisores").json()
    assert listados[0]["email"] == "joao@alphatech.com.br"


def test_atualizar_conta_todos_os_campos(client, criar_icp, fake_account_data):
    """Bug reportado: só dava pra editar nome_fantasia/domínio — segmento,
    CNPJ e os demais campos ficavam travados depois que a conta já existe."""
    icp = criar_icp()
    fake_account_data.candidatos = [_candidato("11222333000191", "Alpha Tech")]
    conta_id = client.post(f"/api/v1/icp/{icp['id']}/contas/gerar", json={"quantidade": 5}).json()["contas"][0]["id"]

    resposta = client.put(
        f"/api/v1/contas/{conta_id}",
        json={
            "nome": "Alpha Tech Consultoria S.A.",
            "cnpj": "99888777000166",
            "nome_fantasia": "Alpha Tech",
            "dominio": "alphatech.com.br",
            "segmento": "Consultoria Financeira",
            "porte": "MEDIO",
            "regiao": "RJ",
        },
    )

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["nome"] == "Alpha Tech Consultoria S.A."
    assert corpo["cnpj"] == "99888777000166"
    assert corpo["segmento"] == "Consultoria Financeira"
    assert corpo["porte"] == "MEDIO"
    assert corpo["regiao"] == "RJ"


def test_atualizar_decisor_move_para_outra_conta(client, criar_icp, fake_account_data):
    """Contato cadastrado na empresa errada, ou que mudou de emprego,
    precisa poder ser movido sem excluir e recriar do zero."""
    icp = criar_icp()
    fake_account_data.candidatos = [
        _candidato("11222333000191", "Alpha Tech"),
        _candidato("22333444000155", "Beta Clinica"),
    ]
    contas = client.post(f"/api/v1/icp/{icp['id']}/contas/gerar", json={"quantidade": 5}).json()["contas"]
    conta_origem_id = contas[0]["id"]
    conta_destino_id = contas[1]["id"]
    decisor_id = client.post(
        f"/api/v1/contas/{conta_origem_id}/decisores", json={"nome": "Joao Silva"}
    ).json()["id"]

    resposta = client.put(
        f"/api/v1/contas/{conta_origem_id}/decisores/{decisor_id}",
        json={"nome": "Joao Silva", "conta_id": conta_destino_id},
    )

    assert resposta.status_code == 200
    assert resposta.json()["conta_id"] == conta_destino_id
    assert client.get(f"/api/v1/contas/{conta_origem_id}/decisores").json() == []
    decisores_destino = client.get(f"/api/v1/contas/{conta_destino_id}/decisores").json()
    assert len(decisores_destino) == 1
    assert decisores_destino[0]["id"] == decisor_id


def test_atualizar_decisor_para_conta_inexistente_falha(client, criar_icp, fake_account_data):
    icp = criar_icp()
    fake_account_data.candidatos = [_candidato("11222333000191", "Alpha Tech")]
    conta_id = client.post(f"/api/v1/icp/{icp['id']}/contas/gerar", json={"quantidade": 5}).json()["contas"][0]["id"]
    decisor_id = client.post(f"/api/v1/contas/{conta_id}/decisores", json={"nome": "Joao Silva"}).json()["id"]

    resposta = client.put(
        f"/api/v1/contas/{conta_id}/decisores/{decisor_id}",
        json={"nome": "Joao Silva", "conta_id": 999999},
    )

    assert resposta.status_code == 404


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


def test_mapear_decisores_soma_qsa_e_enriquecimento(client, criar_icp, fake_account_data, fake_contact_enrichment):
    """Reclamação do usuário: mapear decisores só trazia sócios do QSA,
    nunca C-Levels/Diretores/Gerentes/Heads contratados sem participação
    societária — agora as duas fontes se somam na mesma resposta."""
    icp = criar_icp()
    cnpj = "11222333000191"
    fake_account_data.candidatos = [_candidato(cnpj, "Alpha Tech")]
    fake_account_data.decisores = {cnpj: [DecisorCandidato(cnpj=cnpj, nome="Joao Silva", qualificacao="Sócio")]}
    fake_contact_enrichment.contatos = [
        ContatoCandidato(nome="Maria Diretora", cargo="Diretora Comercial", email="maria@alphatech.com.br"),
    ]
    conta_id = client.post(f"/api/v1/icp/{icp['id']}/contas/gerar", json={"quantidade": 5}).json()["contas"][0]["id"]

    resposta = client.post(f"/api/v1/contas/{conta_id}/decisores/mapear")

    assert resposta.status_code == 200
    decisores = resposta.json()
    assert len(decisores) == 2
    por_nome = {d["nome"]: d for d in decisores}
    assert por_nome["Joao Silva"]["origem"] == "receita_federal_cnpj_qsa"
    assert por_nome["Maria Diretora"]["origem"] == "enriquecimento_contatos"
    assert por_nome["Maria Diretora"]["email"] == "maria@alphatech.com.br"


def test_mapear_decisores_nao_duplica_mesma_pessoa_nas_duas_fontes(
    client, criar_icp, fake_account_data, fake_contact_enrichment
):
    icp = criar_icp()
    cnpj = "11222333000191"
    fake_account_data.candidatos = [_candidato(cnpj, "Alpha Tech")]
    fake_account_data.decisores = {cnpj: [DecisorCandidato(cnpj=cnpj, nome="João Silva", qualificacao="Sócio")]}
    fake_contact_enrichment.contatos = [
        ContatoCandidato(nome="joao silva", cargo="CEO", email="joao@alphatech.com.br", telefone="(11) 90000-0000"),
    ]
    conta_id = client.post(f"/api/v1/icp/{icp['id']}/contas/gerar", json={"quantidade": 5}).json()["contas"][0]["id"]

    resposta = client.post(f"/api/v1/contas/{conta_id}/decisores/mapear")

    assert resposta.status_code == 200
    decisores = resposta.json()
    assert len(decisores) == 1
    # Backfill: nome/origem vêm do QSA (achado primeiro), e-mail/telefone
    # que faltavam vêm do enriquecimento.
    assert decisores[0]["origem"] == "receita_federal_cnpj_qsa"
    assert decisores[0]["email"] == "joao@alphatech.com.br"
    assert decisores[0]["telefone"] == "(11) 90000-0000"


def test_mapear_decisores_funciona_sem_cnpj(client, fake_contact_enrichment):
    """Antes bloqueava com 'Conta sem CNPJ' — agora o enriquecimento roda
    via domínio mesmo sem CNPJ (lead recém-cadastrado, ainda sem CNPJ)."""
    conta_id = client.post(
        "/api/v1/leads/contas", json={"nome": "Beta Clinica", "dominio": "betaclinica.com.br"}
    ).json()["id"]
    fake_contact_enrichment.contatos = [
        ContatoCandidato(nome="Carla Head", cargo="Head de Growth", email="carla@betaclinica.com.br"),
    ]

    resposta = client.post(f"/api/v1/contas/{conta_id}/decisores/mapear")

    assert resposta.status_code == 200
    decisores = resposta.json()
    assert len(decisores) == 1
    assert decisores[0]["nome"] == "Carla Head"
    assert decisores[0]["origem"] == "enriquecimento_contatos"


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


def test_export_pdf_inclui_email_e_telefone_do_decisor(client, criar_icp, fake_account_data, monkeypatch):
    """Raio-X: a lista de decisores exportada precisa levar o contato
    enriquecido (e-mail/telefone), não só nome e cargo."""
    from fpdf import FPDF

    icp = criar_icp()
    fake_account_data.candidatos = [_candidato("11222333000191", "Alpha Tech")]
    conta_id = client.post(f"/api/v1/icp/{icp['id']}/contas/gerar", json={"quantidade": 5}).json()["contas"][0]["id"]
    client.post(
        f"/api/v1/contas/{conta_id}/decisores",
        json={"nome": "Ana Souza", "cargo": "CEO", "email": "ana@alphatech.com.br", "telefone": "+5511988887777"},
    )

    linhas_escritas = []
    cell_original = FPDF.cell

    def cell_espiao(self, *args, **kwargs):
        if "text" in kwargs:
            linhas_escritas.append(kwargs["text"])
        return cell_original(self, *args, **kwargs)

    monkeypatch.setattr(FPDF, "cell", cell_espiao)

    resposta = client.get(f"/api/v1/contas/{conta_id}/export/pdf")

    assert resposta.status_code == 200
    linha_decisor = next(linha for linha in linhas_escritas if linha.startswith("- Ana Souza"))
    assert "ana@alphatech.com.br" in linha_decisor
    assert "+5511988887777" in linha_decisor


def test_export_pdf_normaliza_acento_decomposto(client, criar_icp, fake_account_data, monkeypatch):
    """Raio-X: nome vindo de fornecedor externo (Lusha) pode chegar com
    acento em forma decomposta (NFD) — sem normalizar pra NFC antes do
    encode Latin-1, "César" virava "Ce?sar" no PDF exportado."""
    from fpdf import FPDF

    icp = criar_icp()
    fake_account_data.candidatos = [_candidato("11222333000191", "Alpha Tech")]
    conta_id = client.post(f"/api/v1/icp/{icp['id']}/contas/gerar", json={"quantidade": 5}).json()["contas"][0]["id"]
    nome_nfd = unicodedata.normalize("NFD", "Felipe César")
    client.post(f"/api/v1/contas/{conta_id}/decisores", json={"nome": nome_nfd, "cargo": "Diretor"})

    linhas_escritas = []
    cell_original = FPDF.cell

    def cell_espiao(self, *args, **kwargs):
        if "text" in kwargs:
            linhas_escritas.append(kwargs["text"])
        return cell_original(self, *args, **kwargs)

    monkeypatch.setattr(FPDF, "cell", cell_espiao)

    resposta = client.get(f"/api/v1/contas/{conta_id}/export/pdf")

    assert resposta.status_code == 200
    linha_decisor = next(linha for linha in linhas_escritas if linha.startswith("- Felipe"))
    assert "Felipe César" in linha_decisor
    assert "?" not in linha_decisor


def _id_do_usuario(db_session, email: str) -> int:
    return db_session.query(Usuario).filter_by(email=email).one().id


def test_criar_lead_sem_icp(client):
    """Pedido do usuário: cliente conquistado no varejo (indicação/evento)
    não se enquadra no recorte estático de um ICP — precisa cadastrar sem
    escolher nenhum."""
    resposta = client.post(
        "/api/v1/leads/contas",
        json={"nome": "Consultoria Avulsa Ltda", "dominio": "consultoriaavulsa.com.br"},
    )

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert corpo["nome"] == "Consultoria Avulsa Ltda"
    assert corpo["icp_id"] is None
    assert corpo["origem"] == "lead"
    assert corpo["status"] == "prospectada"


def test_listar_leads_nao_traz_contas_de_icp(client, criar_icp, fake_account_data):
    """Partição estrutural: /leads/contas só lista icp_id IS NULL — contas
    prospectadas via ICP continuam de fora."""
    icp = criar_icp()
    fake_account_data.candidatos = [_candidato("11222333000191", "Alpha Tech")]
    client.post(f"/api/v1/icp/{icp['id']}/contas/gerar", json={"quantidade": 5})
    client.post("/api/v1/leads/contas", json={"nome": "Lead Avulso"})

    leads = client.get("/api/v1/leads/contas").json()

    assert [lead["nome"] for lead in leads] == ["Lead Avulso"]


def test_listar_leads_nao_traz_contas_de_lista_prospeccao(client):
    """Mesma partição de test_listar_leads_nao_traz_contas_de_icp, agora
    pra Lista de Prospecção: uma conta importada por planilha sem ICP
    vinculado não pode aparecer duas vezes (na aba da lista e em
    "Clientes Cadastrados")."""
    lista = client.post("/api/v1/listas-prospeccao", json={"nome": "Evento Teste"}).json()
    client.post(
        f"/api/v1/listas-prospeccao/{lista['id']}/contas/importar-participantes",
        json={"participantes": [{"nome": "Joana Silva", "empresa": "Alpha Tech"}]},
    )
    client.post("/api/v1/leads/contas", json={"nome": "Lead Avulso"})

    leads = client.get("/api/v1/leads/contas").json()

    assert [lead["nome"] for lead in leads] == ["Lead Avulso"]


def test_excluir_todos_os_leads_via_api_super_admin(client):
    """Client de teste já é super_admin por padrão."""
    client.post("/api/v1/leads/contas", json={"nome": "Lead A"})
    client.post("/api/v1/leads/contas", json={"nome": "Lead B"})

    resposta = client.delete("/api/v1/leads/contas")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["apagadas"] == 2
    assert corpo["bloqueadas"] == 0
    assert client.get("/api/v1/leads/contas").json() == []


def test_excluir_todos_os_leads_bloqueia_lead_com_negocio(client, db_session):
    client.post("/api/v1/leads/contas", json={"nome": "Lead Livre"})
    lead_com_negocio = client.post("/api/v1/leads/contas", json={"nome": "Lead Com Negocio"}).json()
    estagio = EstagioFunil(tenant_id=TENANT_ID, nome="Descoberta", ordem=1, tipo="aberto")
    db_session.add(estagio)
    db_session.flush()
    db_session.add(
        Negocio(
            tenant_id=TENANT_ID, conta_id=lead_com_negocio["id"], estagio_id=estagio.id,
            nome="Oportunidade Z", valor=100.0, origem="manual",
        )
    )
    db_session.commit()

    resposta = client.delete("/api/v1/leads/contas")

    corpo = resposta.json()
    assert corpo["apagadas"] == 1
    assert corpo["bloqueadas"] == 1
    assert corpo["detalhes_bloqueadas"][0]["nome"] == "Lead Com Negocio"
    restantes = client.get("/api/v1/leads/contas").json()
    assert [c["nome"] for c in restantes] == ["Lead Com Negocio"]


def test_elegibilidade_exclusao_leads_marca_bloqueados_sem_apagar(client, db_session):
    client.post("/api/v1/leads/contas", json={"nome": "Lead Livre"})
    lead_com_negocio = client.post("/api/v1/leads/contas", json={"nome": "Lead Com Negocio"}).json()
    estagio = EstagioFunil(tenant_id=TENANT_ID, nome="Descoberta", ordem=1, tipo="aberto")
    db_session.add(estagio)
    db_session.flush()
    db_session.add(
        Negocio(
            tenant_id=TENANT_ID, conta_id=lead_com_negocio["id"], estagio_id=estagio.id,
            nome="Oportunidade W", valor=100.0, origem="manual",
        )
    )
    db_session.commit()

    resposta = client.get("/api/v1/leads/contas/elegibilidade-exclusao")

    assert resposta.status_code == 200
    itens = {item["nome"]: item for item in resposta.json()}
    assert itens["Lead Livre"]["bloqueada"] is False
    assert itens["Lead Com Negocio"]["bloqueada"] is True
    assert "negócio" in itens["Lead Com Negocio"]["motivo"]
    # Nada foi apagado — é só pré-visualização.
    assert len(client.get("/api/v1/leads/contas").json()) == 2


def test_excluir_todos_os_leads_com_selecao_manual_restringe_lote(client):
    """Seleção manual (caixas de seleção no frontend) — só os ids enviados
    são tentados, mesmo que outro lead elegível continue existindo."""
    lead_a = client.post("/api/v1/leads/contas", json={"nome": "Lead A"}).json()
    client.post("/api/v1/leads/contas", json={"nome": "Lead B"})

    resposta = client.request("DELETE", "/api/v1/leads/contas", json={"conta_ids": [lead_a["id"]]})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["apagadas"] == 1
    restantes = [c["nome"] for c in client.get("/api/v1/leads/contas").json()]
    assert restantes == ["Lead B"]


def test_limpeza_leads_nao_trabalhados_preview_e_execucao(client, db_session):
    """Regra pontual pedida pelo usuário (2026-08-24): mais solta que
    `DELETE /leads/contas` — só protege quem tem oportunidade OU já foi
    enriquecida (site ou contato)."""
    livre = client.post("/api/v1/leads/contas", json={"nome": "Livre Ltda"}).json()
    com_negocio = client.post("/api/v1/leads/contas", json={"nome": "Com Negocio Ltda"}).json()
    estagio = EstagioFunil(tenant_id=TENANT_ID, nome="Descoberta", ordem=1, tipo="aberto")
    db_session.add(estagio)
    db_session.flush()
    db_session.add(
        Negocio(
            tenant_id=TENANT_ID, conta_id=com_negocio["id"], estagio_id=estagio.id,
            nome="Oportunidade Limpeza", valor=100.0, origem="manual",
        )
    )
    db_session.commit()

    previa = client.get("/api/v1/leads/contas/preview-limpeza-nao-trabalhados").json()
    assert previa == {"total": 2, "serao_apagadas": 1, "protegidas": 1}

    resposta = client.post("/api/v1/leads/contas/limpeza-nao-trabalhados")

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert corpo["apagadas"] == 1
    assert corpo["bloqueadas"] == 1
    restantes = [c["nome"] for c in client.get("/api/v1/leads/contas").json()]
    assert restantes == ["Com Negocio Ltda"]
    assert livre["id"] not in [c["id"] for c in client.get("/api/v1/leads/contas").json()]


def test_limpeza_leads_nao_trabalhados_negada_para_admin(client, criar_usuario_autenticado):
    headers_admin = criar_usuario_autenticado(TENANT_ID, papel="admin", email="admin-limpeza@teste.com.br")

    assert client.get("/api/v1/leads/contas/preview-limpeza-nao-trabalhados", headers=headers_admin).status_code == 403
    assert client.post("/api/v1/leads/contas/limpeza-nao-trabalhados", headers=headers_admin).status_code == 403


def test_excluir_todos_os_leads_negado_para_admin(client, criar_usuario_autenticado):
    headers_admin = criar_usuario_autenticado(TENANT_ID, papel="admin", email="admin-nao-super@teste.com.br")

    resposta = client.delete("/api/v1/leads/contas", headers=headers_admin)

    assert resposta.status_code == 403


def test_excluir_todos_os_leads_negado_para_user(client, criar_usuario_autenticado):
    headers_user = criar_usuario_autenticado(TENANT_ID, papel="user", email="user-nao-super@teste.com.br")

    resposta = client.delete("/api/v1/leads/contas", headers=headers_user)

    assert resposta.status_code == 403


def test_user_so_ve_seus_proprios_leads(client, db_session, criar_usuario_autenticado):
    """Mesma regra de escopo do MAP de contas (saude_conta_service) aplicada
    a leads: vendedor não enxerga a carteira dos colegas."""
    headers_vendedor_a = criar_usuario_autenticado(TENANT_ID, papel="user", email="lead-vendedor-a@teste.com.br")
    headers_vendedor_b = criar_usuario_autenticado(TENANT_ID, papel="user", email="lead-vendedor-b@teste.com.br")

    lead_a = client.post(
        "/api/v1/leads/contas", json={"nome": "Lead do Vendedor A"}, headers=headers_vendedor_a
    ).json()
    vendedor_a_id = _id_do_usuario(db_session, "lead-vendedor-a@teste.com.br")
    conta = db_session.query(Conta).filter_by(id=lead_a["id"]).one()
    conta.vendedor_usuario_id = vendedor_a_id
    db_session.commit()

    leads_a = client.get("/api/v1/leads/contas", headers=headers_vendedor_a).json()
    assert [lead["id"] for lead in leads_a] == [lead_a["id"]]

    leads_b = client.get("/api/v1/leads/contas", headers=headers_vendedor_b).json()
    assert leads_b == []


def test_admin_ve_todos_os_leads_e_filtra_por_vendedor(client, db_session, criar_usuario_autenticado):
    headers_vendedor = criar_usuario_autenticado(TENANT_ID, papel="user", email="lead-vendedor-c@teste.com.br")
    headers_admin = criar_usuario_autenticado(TENANT_ID, papel="admin", email="lead-gestor@teste.com.br")

    lead_vendedor = client.post(
        "/api/v1/leads/contas", json={"nome": "Lead com dono"}, headers=headers_vendedor
    ).json()
    vendedor_id = _id_do_usuario(db_session, "lead-vendedor-c@teste.com.br")
    conta = db_session.query(Conta).filter_by(id=lead_vendedor["id"]).one()
    conta.vendedor_usuario_id = vendedor_id
    db_session.commit()
    client.post("/api/v1/leads/contas", json={"nome": "Lead sem dono"}, headers=headers_admin)

    todos = client.get("/api/v1/leads/contas", headers=headers_admin).json()
    assert len(todos) == 2

    filtrados = client.get(f"/api/v1/leads/contas?vendedor_usuario_id={vendedor_id}", headers=headers_admin).json()
    assert [lead["id"] for lead in filtrados] == [lead_vendedor["id"]]


def test_listar_decisores_leads_respeita_mesmo_escopo(client, db_session, criar_usuario_autenticado):
    headers_vendedor_a = criar_usuario_autenticado(TENANT_ID, papel="user", email="lead-contato-a@teste.com.br")
    headers_vendedor_b = criar_usuario_autenticado(TENANT_ID, papel="user", email="lead-contato-b@teste.com.br")

    lead = client.post(
        "/api/v1/leads/contas", json={"nome": "Empresa com contato"}, headers=headers_vendedor_a
    ).json()
    vendedor_a_id = _id_do_usuario(db_session, "lead-contato-a@teste.com.br")
    conta = db_session.query(Conta).filter_by(id=lead["id"]).one()
    conta.vendedor_usuario_id = vendedor_a_id
    db_session.commit()
    client.post(
        f"/api/v1/contas/{lead['id']}/decisores",
        json={"nome": "Maria Souza", "cargo": "Diretora"},
        headers=headers_vendedor_a,
    )

    decisores_a = client.get("/api/v1/leads/decisores", headers=headers_vendedor_a).json()
    assert [d["nome"] for d in decisores_a] == ["Maria Souza"]

    decisores_b = client.get("/api/v1/leads/decisores", headers=headers_vendedor_b).json()
    assert decisores_b == []


def test_definir_proximo_passo_da_conta(client):
    lead = client.post("/api/v1/leads/contas", json={"nome": "Empresa Y"}).json()

    resposta = client.put(
        f"/api/v1/contas/{lead['id']}/proximo-passo",
        json={"proximo_passo": "Enviar proposta", "proximo_passo_em": "2026-08-10T15:00:00"},
    )

    assert resposta.status_code == 200
    assert resposta.json()["proximo_passo"] == "Enviar proposta"
    assert resposta.json()["proximo_passo_em"].startswith("2026-08-10T15:00:00")


def test_definir_proximo_passo_nao_e_apagado_por_edicao_de_conta(client):
    """Bug evitado por design: editar nome_fantasia/domínio não pode
    apagar um próximo passo já anotado (são endpoints distintos)."""
    lead = client.post("/api/v1/leads/contas", json={"nome": "Empresa X"}).json()
    client.put(
        f"/api/v1/contas/{lead['id']}/proximo-passo",
        json={"proximo_passo": "Ligar semana que vem", "proximo_passo_em": "2026-08-13T10:00:00"},
    )

    resposta = client.put(f"/api/v1/contas/{lead['id']}", json={"nome": "Empresa X", "nome_fantasia": "Empresa X Ltda"})

    assert resposta.status_code == 200
    assert resposta.json()["proximo_passo"] == "Ligar semana que vem"
