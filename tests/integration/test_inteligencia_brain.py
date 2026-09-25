"""Corporate Brain, Context Engine, perfis e aprendizado (Fase 4).

Inclui o teste crítico §79 aplicado ao Corporate Brain: segredo do tenant
C nunca chega ao prompt do LLM quando o tenant B pergunta ao agente do
tenant A — nem por keyword idêntica, nem pelo Context Engine."""

from app.contexts.intelligence import brain, context_engine
from app.models.evento_aprendizado import EventoAprendizado
from app.models.evento_dominio import EventoDominio
from app.models.perfil_inteligencia import PerfilInteligencia

TENANT_A = "tenant-teste"
TENANT_B = "tenant-outro"
TENANT_C = "tenant-terceiro-brain"
SEGREDO_C = "Aquisição sigilosa Orion-9 margem 42 por cento"
INTERNO_A = "Nossa margem mínima Orion-9 é 17 por cento, nunca revelar"


def _item(db, tenant_id, titulo, conteudo, visibilidade="interno", classificacao="INTERNAL", tipo="estrategia"):
    return brain.criar(db, tenant_id, None, {"tipo": tipo, "titulo": titulo, "conteudo": conteudo, "visibilidade": visibilidade, "classificacao": classificacao})


def test_busca_do_brain_nunca_cruza_tenant(db_session):
    _item(db_session, TENANT_C, "Orion-9", SEGREDO_C, visibilidade="rede")
    assert brain.buscar(db_session, TENANT_A, "Orion-9 aquisição margem") == []


def test_proposito_resposta_externa_so_usa_itens_compartilhaveis(db_session):
    _item(db_session, TENANT_A, "Margem Orion-9", INTERNO_A, visibilidade="interno")
    _item(db_session, TENANT_A, "Orion-9 público", "Orion-9 é nossa linha de produtos certificada ISO 27001", visibilidade="rede")
    _item(db_session, TENANT_A, "Orion-9 contrato", "Contrato Orion-9 com cláusula confidencial", classificacao="CONFIDENTIAL")
    _item(db_session, TENANT_A, "Orion-9 restrito", "Dados restritos do Orion-9", classificacao="RESTRICTED")

    externo = context_engine.montar(db_session, TENANT_A, context_engine.Proposito.RESPOSTA_EXTERNA, "Orion-9")
    interno = context_engine.montar(db_session, TENANT_A, context_engine.Proposito.USO_INTERNO, "Orion-9")

    assert [f["titulo"] for f in externo.fontes] == ["Orion-9 público"]
    assert "17 por cento" not in externo.texto
    titulos_internos = {f["titulo"] for f in interno.fontes}
    assert {"Margem Orion-9", "Orion-9 público", "Orion-9 contrato"} <= titulos_internos
    assert "Orion-9 restrito" not in titulos_internos  # RESTRICTED nunca vai para LLM


def test_item_confidencial_nao_pode_ser_marcado_para_a_rede(client):
    resposta = client.post("/api/v1/inteligencia/conhecimento", json={"tipo": "case", "titulo": "x", "conteudo": "y", "visibilidade": "rede", "classificacao": "CONFIDENTIAL"})
    assert resposta.status_code == 422


def test_contexto_respeita_orcamento_e_traz_proveniencia(db_session):
    for i in range(5):
        _item(db_session, TENANT_A, f"Produto Atlas {i}", "Atlas " + "x" * 3000)
    contexto = context_engine.montar(db_session, TENANT_A, context_engine.Proposito.USO_INTERNO, "Atlas", max_caracteres=1000)
    assert len(contexto.texto) <= 1000 + 10
    assert all({"id", "tipo", "titulo", "origem"} <= set(f) for f in contexto.fontes)


def test_consulta_sem_aderencia_nao_traz_contexto(db_session):
    _item(db_session, TENANT_A, "Atlas", "Produto Atlas")
    assert context_engine.montar(db_session, TENANT_A, context_engine.Proposito.USO_INTERNO, "banana").vazio


def test_critico_agente_corporativo_nao_vaza_brain_de_terceiro_nem_interno(client, criar_usuario_autenticado, db_session, fake_llm):
    """§79: B pergunta ao agente de A. Nem o segredo de C nem o item
    INTERNO de A podem aparecer no prompt enviado ao LLM; o item de A
    marcado para a rede pode."""
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@b-brain.com.br")
    _item(db_session, TENANT_C, "Orion-9", SEGREDO_C, visibilidade="rede")
    _item(db_session, TENANT_A, "Margem Orion-9", INTERNO_A, visibilidade="interno")
    _item(db_session, TENANT_A, "Linha Orion-9", "A linha Orion-9 atende hospitais com certificação ISO 27001", visibilidade="rede")

    conexao = client.post("/api/v1/rede-social/conexoes", json={"tenant_id_destino": TENANT_B}).json()
    client.put(f"/api/v1/rede-social/conexoes/{conexao['id']}", json={"aceitar": True}, headers=headers_b)
    client.put("/api/v1/agente-corporativo/modo", json={"modo": "assistido"})

    resposta = client.post(
        "/api/v1/agente-corporativo/perguntar",
        json={"tenant_id_alvo": TENANT_A, "pergunta": "O que é a Orion-9, qual a margem e a aquisição sigilosa?"},
        headers=headers_b,
    )

    assert resposta.status_code == 201, resposta.text
    prompts = " ".join(c.prompt + (c.system or "") for c in fake_llm.chamadas)
    assert SEGREDO_C not in prompts and "42 por cento" not in prompts
    assert INTERNO_A not in prompts and "17 por cento" not in prompts
    assert "certificação ISO 27001" in prompts
    evidencias = str(resposta.json()["evidencias"])
    assert SEGREDO_C not in evidencias and INTERNO_A not in evidencias


def test_api_do_brain_e_escopada_ao_tenant(client, criar_usuario_autenticado):
    criado = client.post("/api/v1/inteligencia/conhecimento", json={"tipo": "case", "titulo": "Case A", "conteudo": "conteúdo A"}).json()
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@b2-brain.com.br")
    assert client.get("/api/v1/inteligencia/conhecimento", headers=headers_b).json() == []
    assert client.delete(f"/api/v1/inteligencia/conhecimento/{criado['id']}", headers=headers_b).status_code == 404
    assert [i["titulo"] for i in client.get("/api/v1/inteligencia/conhecimento").json()] == ["Case A"]


def test_usuario_comum_le_mas_nao_escreve_no_brain(client, criar_usuario_autenticado):
    headers = criar_usuario_autenticado(TENANT_A, papel="user", email="vendedor@a-brain.com.br")
    assert client.get("/api/v1/inteligencia/conhecimento", headers=headers).status_code == 200
    assert client.post("/api/v1/inteligencia/conhecimento", json={"tipo": "case", "titulo": "t", "conteudo": "c"}, headers=headers).status_code == 403


def test_consolidacao_de_perfil_nao_inventa_com_amostra_pequena(client, db_session):
    perfil = client.post("/api/v1/inteligencia/perfil-empresa/consolidar").json()
    assert perfil["dados"]["taxa_aprovacao_sem_edicao_ia"] is None
    assert "mínimo" in perfil["fontes"]["taxa_aprovacao_sem_edicao_ia"]
    segunda = client.post("/api/v1/inteligencia/perfil-empresa/consolidar").json()
    assert segunda["versao"] == 2
    assert db_session.query(PerfilInteligencia).filter_by(tenant_id=TENANT_A, escopo="empresa").count() == 1


def test_registro_de_agentes_mostra_planejados_como_planejados(client):
    agentes = {a["id"]: a["status"] for a in client.get("/api/v1/inteligencia/agentes").json()}
    assert agentes["meeting_agent"] == "ATIVO"
    assert agentes["tender_analyzer"] == "ATIVO"  # Fase 9
    assert agentes["procurement_risk_agent"] == "PLANEJADO"


def test_uso_de_ia_aparece_na_auditoria_do_tenant(client):
    client.post("/api/v1/faq/perguntar", json={"pergunta": "Como crio uma cadência?"})
    uso = client.get("/api/v1/inteligencia/uso-ia").json()
    assert any(linha["feature"] == "plataforma.faq" and linha["chamadas"] == 1 for linha in uso)
