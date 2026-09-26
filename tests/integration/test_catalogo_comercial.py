"""Catálogo comercial e assinatura (Fase 14). GATE: página pública e área
interna refletem os produtos disponíveis; nada não lançado aparece como
disponível; Public Procurement sem preço."""

from app.api.deps import get_plan_limits_provider
from app.core.config import settings
from app.main import app
from app.models.cadencia import Cadencia
from app.models.plano import Plano
from app.models.registro_uso_ia import RegistroUsoIa
from app.providers.plan_limits.stub import StubPlanLimitsProvider

TENANT = "tenant-teste"
PRODUTOS_DO_PROMPT = {"crm", "map", "predator", "business_network", "opportunity_intelligence", "bid_intelligence",
                      "public_procurement", "api_access", "connectors", "ai_credits",
                      "strategic_sourcing", "strategic_sourcing_enterprise"}  # Phase I (D-059)


def _produtos(client) -> dict:
    resposta = client.get("/api/v1/catalogo", headers={"Authorization": ""})
    assert resposta.status_code == 200, resposta.text
    return {p["id"]: p for p in resposta.json()["produtos"]}


def test_catalogo_publico_representa_todos_os_produtos_do_escopo(client):
    produtos = _produtos(client)
    assert set(produtos) == PRODUTOS_DO_PROMPT
    assert {produtos[p]["disponibilidade"] for p in ("crm", "map", "predator")} == {"DISPONIVEL"}
    assert produtos["business_network"]["disponibilidade"] == "GRATUITO"
    assert produtos["opportunity_intelligence"]["disponibilidade"] == "INCLUIDO"
    assert "Plano Padrão Teste" in produtos["crm"]["planos"]


def test_public_procurement_nunca_tem_preco_nem_fica_disponivel(client, db_session):
    # mesmo que um plano self-service o inclua por engano, continua em definição
    db_session.add(Plano(nome="Plano Errado", franquia_contas_mes=1, preco_mensal=10.0, modulos_contratados=["procurement", "bids"]))
    db_session.commit()
    procurement = _produtos(client)["public_procurement"]
    assert (procurement["disponibilidade"], procurement["status_preco"], procurement["planos"]) == ("EM_DEFINICAO", "PENDING_DEFINITION", [])
    pendente = procurement["precificacao_pendente"]
    assert {"preco_mensal", "preco_anual", "usuarios_incluidos", "creditos_ia", "regras_de_excedente"} <= set(pendente)
    assert set(pendente.values()) == {None}  # estrutura pronta, nenhum valor inventado
    # Phase I (D-059): Bid Intelligence tem preço aprovado; fica disponível quando um plano self-service o inclui
    bids = _produtos(client)["bid_intelligence"]
    assert (bids["disponibilidade"], bids["status_preco"], bids["planos"]) == ("DISPONIVEL", "DEFINIDO", ["Plano Errado"])


def test_nada_nao_lancado_aparece_como_disponivel(client, monkeypatch):
    produtos = _produtos(client)
    for produto in produtos.values():
        if produto["disponibilidade"] == "DISPONIVEL" and produto["id"] != "ai_credits":
            assert produto["planos"], f"{produto['id']} disponível sem plano que o inclua"
            assert produto["status_preco"] == "DEFINIDO"
    conectores = {c["sistema"]: c for c in produtos["connectors"]["conectores"]}
    assert conectores["b2bon_crm"]["disponibilidade"] == "INCLUIDO"
    assert all(c["disponibilidade"] == "BETA" and not c["liberado_para_conexao"]
               for s, c in conectores.items() if s != "b2bon_crm")
    assert produtos["connectors"]["disponibilidade"] == "BETA"
    assert produtos["ai_credits"]["disponibilidade"] == "DISPONIVEL"  # Fase 15: pacotes do catálogo versionado
    assert {p["codigo"] for p in produtos["ai_credits"]["pacotes"]} >= {"AI_START", "AI_1M", "ENTERPRISE"}

    monkeypatch.setattr(settings, "conectores_crm_habilitados", "hubspot")
    conectores = {c["sistema"]: c for c in _produtos(client)["connectors"]["conectores"]}
    assert conectores["hubspot"]["liberado_para_conexao"] and not conectores["salesforce"]["liberado_para_conexao"]


def test_plano_sem_self_service_nao_entra_no_catalogo_publico(client, db_session):
    db_session.add(Plano(nome="Teste Convite", franquia_contas_mes=1, preco_mensal=0.0, visivel_self_service=False,
                         modulos_contratados=["map"]))
    db_session.commit()
    nomes = [p["nome"] for p in client.get("/api/v1/catalogo").json()["planos"]]
    assert "Teste Convite" not in nomes and "Plano Padrão Teste" in nomes


def test_assinatura_mostra_plano_modulos_uso_e_ia_do_proprio_tenant(client, db_session, criar_usuario_autenticado, monkeypatch):
    # o stub dos testes libera tudo; aqui ele espelha o plano (sem bids/procurement)
    monkeypatch.setitem(app.dependency_overrides, get_plan_limits_provider,
                        lambda: StubPlanLimitsProvider(modulos_bloqueados={TENANT: {"bids", "procurement", "sourcing", "sourcing_enterprise"}}))
    db_session.add(Cadencia(tenant_id=TENANT, nome="Cadência do mês", status="rascunho"))
    db_session.add(RegistroUsoIa(tenant_id=TENANT, agente="crm_meeting_agent", feature="crm.teste", modulo="crm", status="sucesso",
                               tokens_entrada=10, tokens_saida=5, latencia_ms=100))
    db_session.commit()
    assinatura = client.get("/api/v1/assinatura").json()
    assert assinatura["plano"]["nome"] == "Plano Padrão Teste" and assinatura["licenca"]["status"] == "ativa"
    modulos = {m["modulo"]: m for m in assinatura["modulos"]}
    assert {k for k, m in modulos.items() if m["contratado"]} == {"map", "predator", "crm"}
    assert modulos["procurement"]["disponibilidade"] == "EM_DEFINICAO" and not modulos["procurement"]["contratado"]
    assert assinatura["uso"]["usuarios"] == {"usado": 1, "limite": 50, "percentual": 2}
    assert assinatura["uso"]["cadencias"]["usado"] == 1
    assert assinatura["ia"]["chamadas_no_mes"] == 1 and "custo_usd" not in str(assinatura)

    outro = criar_usuario_autenticado("tenant-outro-assinatura", papel="user", email="u@outro-assinatura.com")
    do_outro = client.get("/api/v1/assinatura", headers=outro).json()
    assert do_outro["uso"]["cadencias"]["usado"] == 0 and do_outro["ia"]["chamadas_no_mes"] == 0


def test_assinatura_reflete_o_entitlement_real(client, monkeypatch):
    monkeypatch.setitem(app.dependency_overrides, get_plan_limits_provider,
                        lambda: StubPlanLimitsProvider(modulos_bloqueados={TENANT: {"predator"}}))
    modulos = {m["modulo"]: m["contratado"] for m in client.get("/api/v1/assinatura").json()["modulos"]}
    assert modulos["predator"] is False and modulos["crm"] is True


def test_assinatura_exige_login(client):
    assert client.get("/api/v1/assinatura", headers={"Authorization": ""}).status_code == 401
