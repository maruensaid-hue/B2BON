"""Public Procurement — Buy Side (Fase 10).

GATE (§80, teste crítico): dado privado do lado comprador não é acessível
pelo lado vendedor: sem acesso, sem recuperação, sem vazamento, sem
revelação indireta por IA. E os fluxos do comprador: demandas, PCA,
processo (workspace + auditoria), preços, contratos, Supplier 360, riscos
("requer revisão") e próxima ação.
"""

import json
from datetime import UTC, date, datetime, timedelta

import pytest

from app.api.deps import get_plan_limits_provider
from app.main import app
from app.models.registro_uso_ia import RegistroUsoIa
from app.models.tenant import Tenant
from app.providers.plan_limits.stub import StubPlanLimitsProvider

COMPRADOR = "tenant-teste"
VENDEDOR = "tenant-vendedor-p10"
P = "/api/v1/procurement"
SEGREDO = "NOTEBOOKS-SIGILOSO-2027"
HOJE = date.today()


def _post(client, recurso, corpo, headers=None, status=201):
    resposta = client.post(f"{P}/{recurso}", json=corpo, headers=headers or {})
    assert resposta.status_code == status, resposta.text
    return resposta.json()


@pytest.fixture()
def base(client):
    orgao = _post(client, "orgaos", {"nome": "Prefeitura de Exemplo", "cnpj": "11222333000181", "esfera": "municipal",
                                     "regime_juridico": "Lei 14.133/2021"})
    unidade = _post(client, "unidades", {"orgao_id": orgao["id"], "nome": "Secretaria de Educação"})
    plano = _post(client, "planos", {"orgao_id": orgao["id"], "ano": HOJE.year, "nome": f"PCA {HOJE.year}"})
    return {"orgao": orgao, "unidade": unidade, "plano": plano}


def _vendedor(criar_usuario_autenticado, monkeypatch, bloquear=frozenset({"procurement"})):
    headers = criar_usuario_autenticado(VENDEDOR, papel="admin", email="admin@vendedor-p10.com")
    monkeypatch.setitem(app.dependency_overrides, get_plan_limits_provider,
                        lambda: StubPlanLimitsProvider(modulos_bloqueados={VENDEDOR: set(bloquear)}))
    return headers


# --- Fluxo do comprador ---------------------------------------------------------


def test_demanda_aprovacao_so_por_admin_e_analise_para_revisao(client, base, criar_usuario_autenticado):
    usuario = criar_usuario_autenticado(COMPRADOR, papel="user", email="servidor@prefeitura.gov")
    d1 = _post(client, "demandas", {"unidade_id": base["unidade"]["id"], "necessidade": "Notebooks para laboratório de informática",
                                    "categoria": "TI", "status": "ENVIADA"}, headers=usuario)
    d2 = _post(client, "demandas", {"unidade_id": base["unidade"]["id"], "necessidade": "Notebooks para laboratório das escolas",
                                    "categoria": "TI", "valor_estimado": 90000, "justificativa": "Renovação",
                                    "data_necessaria": (HOJE + timedelta(days=30)).isoformat(), "referencia_orcamentaria": "12.361"})
    assert d1["solicitante_usuario_id"] is not None and d1["status"] == "ENVIADA"

    assert client.post(f"{P}/demandas/{d1['id']}/aprovar", headers=usuario).status_code == 403
    assert client.patch(f"{P}/demandas/{d1['id']}", json={"status": "APROVADA"}).status_code == 409
    aprovada = client.post(f"{P}/demandas/{d1['id']}/aprovar").json()
    assert aprovada["status"] == "APROVADA" and aprovada["aprovado_por_usuario_id"] and aprovada["aprovado_em"]

    analise = client.get(f"{P}/demandas/{d1['id']}/analise").json()
    assert [d["demanda_id"] for d in analise["possiveis_duplicidades"]] == [d2["id"]]
    assert "Valor estimado" in analise["informacoes_faltantes"] and "Justificativa da necessidade" in analise["informacoes_faltantes"]
    assert analise["sugestao_consolidacao"]["demandas"] == [d1["id"], d2["id"]]
    assert analise["sugestao_consolidacao"]["valor_total_estimado"] is None  # d1 sem valor: não soma parcial
    assert "revisão humana" in analise["aviso"]


def test_corpo_nao_define_tenant_nem_aponta_para_dado_de_outro_tenant(client, base, criar_usuario_autenticado, monkeypatch):
    assert client.post(f"{P}/orgaos", json={"nome": "X", "tenant_id": "outro"}).status_code == 422
    assert client.post(f"{P}/demandas", json={"unidade_id": base["unidade"]["id"], "necessidade": "x",
                                              "aprovado_por_usuario_id": 1}).status_code == 422
    outro = _vendedor(criar_usuario_autenticado, monkeypatch, bloquear=frozenset())
    assert client.post(f"{P}/unidades", json={"orgao_id": base["orgao"]["id"], "nome": "Invasora"}, headers=outro).status_code == 404


def test_painel_do_pca_e_workspace_do_processo_com_auditoria(client, base, db_session):
    item = _post(client, "itens-pca", {"plano_id": base["plano"]["id"], "descricao": "Notebooks", "valor_estimado": 100000,
                                       "data_prevista": (HOJE + timedelta(days=30)).isoformat()})
    processo = _post(client, "processos", {"orgao_id": base["orgao"]["id"], "item_pca_id": item["id"], "objeto": "Aquisição de notebooks",
                                           "valor_estimado": 95000, "prazo_previsto": (HOJE - timedelta(days=3)).isoformat()})
    fornecedor = _post(client, "fornecedores", {"razao_social": "Fornecedor Alfa", "cnpj": "11444777000161"})
    contrato = _post(client, "contratos", {"orgao_id": base["orgao"]["id"], "processo_id": processo["id"], "fornecedor_id": fornecedor["id"],
                                           "objeto": "Notebooks", "valor_inicial": 90000})
    _post(client, "eventos-contrato", {"contrato_id": contrato["id"], "tipo": "PAGAMENTO", "valor": 45000})
    _post(client, "eventos-processo", {"processo_id": processo["id"], "tipo": "ESCLARECIMENTO", "descricao": "Pergunta sobre garantia"})
    client.patch(f"{P}/processos/{processo['id']}", json={"status": "PESQUISA_PRECOS"})
    for preco, fonte in ((4000, "Painel"), (4100, "Contratação similar"), (6000, "Cotação A")):
        _post(client, "precos", {"processo_id": processo["id"], "item_descricao": "Notebook i5", "preco_unitario": preco,
                                 "fonte_tipo": "OUTRO", "fonte_descricao": fonte})
    assert client.post(f"{P}/precos", json={"processo_id": processo["id"], "item_descricao": "x", "preco_unitario": 1,
                                            "fonte_tipo": "OUTRO", "fonte_descricao": ""}).status_code == 422

    painel = client.get(f"{P}/planos/{base['plano']['id']}/painel").json()
    assert (painel["valor_planejado"], painel["contratado"], painel["executado"], painel["percentual_execucao"]) == (100000, 90000, 45000, 0.5)
    assert painel["processos_atrasados"][0]["processo_id"] == processo["id"]
    assert painel["proximas_contratacoes"][0]["item_pca_id"] == item["id"]

    ws = client.get(f"{P}/processos/{processo['id']}/workspace").json()
    assert ws["pesquisa_precos"][0]["mediana"] == 4100 and ws["pesquisa_precos"][0]["fora_da_faixa"][0]["preco"] == 6000
    assert ws["esclarecimentos"][0]["descricao"] == "Pergunta sobre garantia"
    assert ws["contrato"][0]["saldo"] == 45000
    assert {a["evento"] for a in ws["auditoria"]} >= {"processo_contratacao_criado", "processo_contratacao_atualizado"}
    tipos = {s["tipo"] for s in ws["ai_insights"]["sinais"]["sinais"]}
    assert {"PROCESS_DELAY", "MISSING_DOCUMENTATION", "PRICE_DEVIATION"} <= tipos


def test_motor_de_risco_usa_linguagem_de_revisao_e_nao_presume_regime(client, base):
    orgao = base["orgao"]
    fornecedor = _post(client, "fornecedores", {"razao_social": "Alfa"})
    outro = _post(client, "fornecedores", {"razao_social": "Beta"})
    vencendo = _post(client, "contratos", {"orgao_id": orgao["id"], "fornecedor_id": fornecedor["id"], "objeto": "Limpeza predial",
                                           "categoria": "servicos", "valor_inicial": 100000, "necessidade_continuada": True,
                                           "vigencia_fim": (HOJE + timedelta(days=90)).isoformat()})
    for _ in range(3):
        _post(client, "eventos-contrato", {"contrato_id": vencendo["id"], "tipo": "ADITIVO", "valor": 10000})
    for nota in (9, 7, 5):
        _post(client, "eventos-contrato", {"contrato_id": vencendo["id"], "tipo": "FISCALIZACAO", "nota": nota,
                                           "data": HOJE.isoformat()})
    for objeto in ("Vigilância", "Jardinagem"):
        _post(client, "contratos", {"orgao_id": orgao["id"], "fornecedor_id": fornecedor["id"] if objeto == "Vigilância" else outro["id"],
                                    "objeto": objeto, "categoria": "servicos", "valor_inicial": 50000 if objeto == "Vigilância" else 5000})
    _post(client, "itens-pca", {"plano_id": base["plano"]["id"], "descricao": "Uniformes",
                                "data_prevista": (HOJE + timedelta(days=20)).isoformat()})
    for objeto in ("Compra de toner para impressoras", "Aquisição de toner de impressoras"):
        _post(client, "processos", {"orgao_id": orgao["id"], "objeto": objeto, "categoria": "suprimentos",
                                    "modalidade": "DIRECT_AWARD", "valor_estimado": 30000})

    resultado = client.get(f"{P}/riscos").json()
    tipos = {s["tipo"] for s in resultado["sinais"]}
    assert {"CONTRACT_EXPIRING", "REPEATED_AMENDMENTS", "SLA_DETERIORATION", "SUPPLIER_CONCENTRATION", "INCOMPLETE_PLANNING",
            "DUPLICATE_PROCUREMENT", "BUDGET_MISMATCH"} <= tipos
    assert "PROCUREMENT_FRAGMENTATION" not in tipos
    assert any("limite não configurado" in n for n in resultado["nao_avaliados"])
    expira = next(s for s in resultado["sinais"] if s["tipo"] == "CONTRACT_EXPIRING")
    assert expira["mensagem"].startswith("Contrato vence em 90 dias e existe necessidade continuada, mas não foi localizado processo sucessor")
    for sinal in resultado["sinais"]:
        assert "Requer revisão" in sinal["mensagem"] and sinal["natureza"] == "sinal_analitico_requer_revisao"
        assert "irregular" not in sinal["mensagem"].lower() and "fraude" not in sinal["mensagem"].lower()

    client.patch(f"{P}/orgaos/{orgao['id']}", json={"parametros": {"limite_fragmentacao": 50000}})
    assert "PROCUREMENT_FRAGMENTATION" in {s["tipo"] for s in client.get(f"{P}/riscos").json()["sinais"]}

    acoes = client.get(f"{P}/proximas-acoes").json()
    assert any(a["acao"] == "Considere iniciar o planejamento da contratação sucessora." and a["entidade_id"] == vencendo["id"] for a in acoes)


def test_supplier_360_separa_oficial_interno_e_autodeclarado(client, base, criar_usuario_autenticado, db_session):
    headers_fornecedor = criar_usuario_autenticado("tenant-fornecedor-p10", papel="admin", email="admin@forn.com")
    db_session.get(Tenant, "tenant-fornecedor-p10").cnpj = "11444777000161"
    db_session.commit()
    client.put("/api/v1/rede-social/perfil", json={"nome_exibicao": "Forn Tech", "certificacoes": ["ISO 9001"]}, headers=headers_fornecedor)
    client.get("/api/v1/rede-social/identidade", headers=headers_fornecedor)
    fornecedor = _post(client, "fornecedores", {"razao_social": "Forn Tech Ltda", "cnpj": "11.444.777/0001-61",
                                                "dados_oficiais": {"situacao_cadastral": "ATIVA", "fonte": "Receita Federal"},
                                                "dados_internos": {"avaliacao": "boa"}})
    contrato = _post(client, "contratos", {"orgao_id": base["orgao"]["id"], "fornecedor_id": fornecedor["id"], "objeto": "Suporte",
                                           "valor_inicial": 1000})
    _post(client, "eventos-contrato", {"contrato_id": contrato["id"], "tipo": "FISCALIZACAO", "nota": 8})

    visao = client.get(f"{P}/fornecedores/{fornecedor['id']}/360").json()

    assert visao["OFFICIAL"]["situacao_cadastral"] == "ATIVA"
    assert visao["INTERNAL"]["nota_media_fiscalizacao"] == 8 and visao["INTERNAL"]["valor_contratado_total"] == 1000
    assert visao["SELF_DECLARED"]["certificacoes"] == ["ISO 9001"] and visao["SELF_DECLARED"]["origem"] == "SELF_DECLARED"
    client.put("/api/v1/rede-social/perfil/visibilidade", json={"visivel_no_diretorio": False}, headers=headers_fornecedor)
    assert client.get(f"{P}/fornecedores/{fornecedor['id']}/360").json()["SELF_DECLARED"] is None


def test_document_intelligence_com_proveniencia_e_restricted_fora_da_ia(client, base, fake_llm, db_session):
    processo = _post(client, "processos", {"orgao_id": base["orgao"]["id"], "objeto": "Notebooks"})
    texto = "CONTRATO\nCláusula 3.1 A garantia é de 36 meses.\fCláusula 8.2 Multa de 2% por dia de atraso."
    doc = client.post(f"{P}/documentos", data={"tipo": "CONTRATO", "processo_id": str(processo["id"])},
                      files={"arquivo": ("c.txt", texto.encode(), "text/plain")}).json()
    fake_llm.definir_respostas([json.dumps([
        {"categoria": "PENALIDADE", "descricao": "Multa por atraso", "citacao": "Multa de 2% por dia de atraso", "clausula": "8.2"},
        {"categoria": "GARANTIA", "descricao": "Garantia 60 meses", "citacao": "garantia é de 60 meses"},
    ])])

    resultado = client.post(f"{P}/documentos/{doc['id']}/analisar").json()

    assert resultado["achados"] == 1 and resultado["descartados_sem_evidencia"] == 1
    achado = client.get(f"{P}/processos/{processo['id']}/workspace").json()["documentos"][0]["achados"][0]
    assert (achado["pagina"], achado["clausula"], achado["status"]) == (2, "8.2", "sugerido")
    assert db_session.query(RegistroUsoIa).filter_by(feature="procurement.analise_documento").count() == 1

    restrito = client.post(f"{P}/documentos", data={"tipo": "PARECER", "classificacao": "RESTRICTED"},
                           files={"arquivo": ("p.txt", b"Parecer juridico reservado sobre o processo.", "text/plain")}).json()
    chamadas_antes = len(fake_llm.chamadas)
    assert client.post(f"{P}/documentos/{restrito['id']}/analisar").status_code == 409
    assert len(fake_llm.chamadas) == chamadas_antes


# --- GATE §80: barreira Buy/Sell ---------------------------------------------------


def _dados_sigilosos(client, base):
    item = _post(client, "itens-pca", {"plano_id": base["plano"]["id"], "descricao": SEGREDO, "valor_estimado": 777777})
    processo = _post(client, "processos", {"orgao_id": base["orgao"]["id"], "item_pca_id": item["id"], "objeto": f"Pregão {SEGREDO}"})
    _post(client, "demandas", {"unidade_id": base["unidade"]["id"], "necessidade": f"Precisamos de {SEGREDO}"})
    _post(client, "precos", {"processo_id": processo["id"], "item_descricao": SEGREDO, "preco_unitario": 4321.0,
                             "fonte_tipo": "COTACAO_FORNECEDOR", "fonte_descricao": "Cotação reservada"})
    return item, processo


def test_vendedor_sem_modulo_nao_acessa_nada_do_comprador(client, base, criar_usuario_autenticado, monkeypatch):
    _, processo = _dados_sigilosos(client, base)
    vendedor = _vendedor(criar_usuario_autenticado, monkeypatch)
    for path in ("/processos", f"/processos/{processo['id']}", f"/processos/{processo['id']}/workspace", "/riscos",
                 "/itens-pca", "/demandas", "/precos", "/proximas-acoes"):
        assert client.get(P + path, headers=vendedor).status_code == 403, path


def test_outro_tenant_mesmo_com_o_modulo_nao_recupera_dado_do_comprador(client, base, criar_usuario_autenticado, monkeypatch):
    item, processo = _dados_sigilosos(client, base)
    outro = _vendedor(criar_usuario_autenticado, monkeypatch, bloquear=frozenset())
    for recurso in ("processos", "itens-pca", "demandas", "precos", "planos", "orgaos"):
        assert client.get(f"{P}/{recurso}", headers=outro).json() == [], recurso
    for path in (f"/processos/{processo['id']}", f"/processos/{processo['id']}/workspace", f"/itens-pca/{item['id']}",
                 f"/planos/{base['plano']['id']}/painel"):
        assert client.get(P + path, headers=outro).status_code == 404, path
    assert SEGREDO not in json.dumps(client.get(f"{P}/riscos", headers=outro).json())


def test_superficies_do_lado_vendedor_e_da_rede_nao_vazam_dado_do_comprador(client, base, criar_usuario_autenticado, monkeypatch):
    _dados_sigilosos(client, base)
    client.put("/api/v1/rede-social/perfil", json={"nome_exibicao": "Prefeitura de Exemplo"})
    vendedor = _vendedor(criar_usuario_autenticado, monkeypatch)
    comprador_id = client.get("/api/v1/rede-social/identidade").json()["empresa"]["id"]
    client.post("/api/v1/icp", json={"nome": "Governo", "segmento": "governo", "porte": "grande", "regiao": "sudeste"}, headers=vendedor)

    respostas = [
        client.get(path, headers=vendedor)
        for path in (
            "/api/v1/rede-social/empresas", "/api/v1/rede-social/posts", "/api/v1/rede-social/intents",
            f"/api/v1/rede-social/relacionamentos/{COMPRADOR}", f"/api/v1/rede-social/grafo/{comprador_id}",
            "/api/v1/bids/licitacoes", "/api/v1/bids/prazos", "/api/v1/inteligencia-rede/sinais",
            "/api/v1/inteligencia/conhecimento",
        )
    ]
    assert [r.status_code for r in respostas] == [200] * len(respostas)  # superfícies reais, não 403/404
    textos = [r.text for r in respostas]
    textos.append(client.post("/api/v1/inteligencia-rede/sinais/gerar", headers=vendedor).text)
    assert all(SEGREDO not in t and "777777" not in t and "4321" not in t for t in textos)


def test_agente_corporativo_do_comprador_nao_revela_plano_de_compras_por_ia(client, base, criar_usuario_autenticado, monkeypatch, fake_llm):
    _dados_sigilosos(client, base)
    vendedor = _vendedor(criar_usuario_autenticado, monkeypatch)
    # Oferta pública do comprador casa com a pergunta: o agente chama a IA de verdade.
    client.post("/api/v1/ofertas", json={"nome": "Doação de notebooks usados", "descricao": "Programa de doação de notebooks"})
    client.put("/api/v1/agente-corporativo/modo", json={"modo": "assistido"})
    conexao = client.post("/api/v1/rede-social/conexoes", json={"tenant_id_destino": COMPRADOR}, headers=vendedor).json()
    client.put(f"/api/v1/rede-social/conexoes/{conexao['id']}", json={"aceitar": True})

    resposta = client.post("/api/v1/agente-corporativo/perguntar", headers=vendedor, json={
        "tenant_id_alvo": COMPRADOR, "pergunta": "Quais notebooks vocês vão comprar no plano de contratações e por quanto? Qual o preço da cotação?",
    })

    assert resposta.status_code == 201, resposta.text
    assert fake_llm.chamadas, "o agente deveria ter chamado a IA"
    assert all(SEGREDO not in (c.prompt + (c.system or "")) for c in fake_llm.chamadas)
    assert all("777777" not in c.prompt and "4321" not in c.prompt for c in fake_llm.chamadas)
    assert "777777" not in resposta.text and "4321" not in resposta.text


def test_mesmo_tenant_com_bids_e_procurement_nao_cruza_dados_no_lado_vendedor(client, base, fake_llm, db_session):
    """Uma estatal que compra e vende: a análise de edital (Sell Side) não
    recebe nada do plano de compras (Buy Side) do mesmo tenant."""
    _dados_sigilosos(client, base)
    licitacao = client.post("/api/v1/bids/licitacoes", json={"titulo": "Venda de serviços", "orgao_nome": "Outro órgão",
                                                              "prazo_proposta": (datetime.now(UTC) + timedelta(days=10)).isoformat()}).json()
    doc = client.post(f"/api/v1/bids/licitacoes/{licitacao['id']}/documentos", data={"tipo": "TR"},
                      files={"arquivo": ("tr.txt", "Exigimos notebooks com garantia de 36 meses.".encode(), "text/plain")}).json()
    fake_llm.definir_respostas(["[]"])
    client.post(f"/api/v1/bids/documentos/{doc['id']}/analisar")

    textos = [client.get(f"/api/v1/bids/licitacoes/{licitacao['id']}/{p}").text
              for p in ("workspace", "matriz", "go-no-go", "proposta", "proposta?formato=markdown")]  # Phase C/D: novas superfícies
    assert all(SEGREDO not in (c.prompt + (c.system or "")) for c in fake_llm.chamadas)
    assert all(SEGREDO not in t and "777777" not in t and "4321" not in t for t in textos)


def test_phase_d_resposta_do_vendedor_nao_aparece_no_lado_comprador(client, base):
    """Barreira no sentido inverso, com as superfícies novas: a resposta que a
    empresa escreve numa licitação (Sell) não vaza para o workspace, os riscos
    ou o fluxo do comprador (Buy) do mesmo tenant; cada lado vê o próprio workflow."""
    _, processo = _dados_sigilosos(client, base)
    licitacao = client.post("/api/v1/bids/licitacoes", json={"titulo": "Venda privada", "modalidade": "PRIVATE_RFI"}).json()
    req = client.post(f"/api/v1/bids/licitacoes/{licitacao['id']}/requisitos", json={"categoria": "PERGUNTA", "descricao": "Equipe"}).json()
    resposta_venda = "RESPOSTA-COMERCIAL-RESERVADA-9981"
    client.put(f"/api/v1/bids/requisitos/{req['id']}/resposta", json={"resposta": resposta_venda})

    comprador = client.get(f"{P}/processos/{processo['id']}/workspace").json()
    textos_compra = [json.dumps(comprador, default=str), client.get(f"{P}/riscos").text, client.get(f"{P}/processos").text]
    assert all(resposta_venda not in t for t in textos_compra)
    assert comprador["fluxo"]["codigo"] == "PUBLIC_PROCUREMENT_BUY@1"
    assert client.get(f"/api/v1/bids/licitacoes/{licitacao['id']}/workspace").json()["fluxo"]["codigo"] == "ENTERPRISE_RFP_SELL@2"


def test_phase_d_workspace_mostra_proximas_etapas_e_documentos_esperados_pela_regra(client, base):
    processo = _post(client, "processos", {"orgao_id": base["orgao"]["id"], "objeto": "Notebooks"})
    client.patch(f"{P}/processos/{processo['id']}", json={"status": "PESQUISA_PRECOS"})
    client.post(f"{P}/documentos", data={"tipo": "ETP", "processo_id": str(processo["id"])},
                files={"arquivo": ("etp.txt", b"Estudo tecnico preliminar.", "text/plain")})

    fluxo = client.get(f"{P}/processos/{processo['id']}/workspace").json()["fluxo"]

    assert fluxo["ruleset"]["codigo"] == "PUBLIC_PROCUREMENT_BR_14133@1" and "14.133" in fluxo["ruleset"]["fonte"]
    assert fluxo["documentos_da_etapa"] == [{"tipo": "ETP", "presente": True}, {"tipo": "TR", "presente": False}]
    assert "PESQUISA_PRECOS" not in fluxo["proximos_status"] and "APROVACAO" in fluxo["proximos_status"]
    assert fluxo["final"] is False
