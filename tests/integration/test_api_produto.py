"""API de produto (Fase 3): chaves, escopos, entitlement, isolamento,
idempotência, rate limit, correlation id e contrato OpenAPI."""

from datetime import UTC, datetime, timedelta

import pytest

from app.api.deps import API_LIMITE_POR_MINUTO, get_plan_limits_provider
from app.contexts.integrations.adapters.b2bon_crm import B2BOnCrmAdapter
from app.contexts.integrations.contract import iterar_todos
from app.main import app
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.evento_dominio import EventoDominio
from app.models.interacao_conta import InteracaoConta
from app.models.licenca import Licenca
from app.providers.account_data.base import ContaCandidata
from app.providers.plan_limits.stub import StubPlanLimitsProvider
from app.services import crm_service

TENANT_ID = "tenant-teste"
TENANT_B = "tenant-b-api"
PERIODO = datetime.now(UTC).strftime("%Y-%m")


def _chave(client, escopos, headers=None) -> str:
    resposta = client.post("/api/v1/chaves-api", json={"nome": "integração", "escopos": escopos}, headers=headers or {})
    assert resposta.status_code == 201, resposta.text
    return resposta.json()["segredo"]


def _dados_crm(db, tenant_id: str, nome: str):
    agora = datetime.now(UTC)
    ganho = next(e for e in crm_service.garantir_estagios_padrao(db, tenant_id) if e.tipo == "ganho")
    conta = Conta(tenant_id=tenant_id, nome=nome, status="prospectada", criado_em=agora - timedelta(days=20))
    db.add(conta)
    db.commit()
    decisor = Decisor(tenant_id=tenant_id, conta_id=conta.id, nome="D")
    db.add(decisor)
    db.commit()
    negocio = crm_service.criar_negocio(db, tenant_id, None, conta.id, decisor.id, f"N {nome}", valor=5000.0)
    crm_service.mover_estagio(db, tenant_id, None, negocio.id, ganho.id)
    db.add(InteracaoConta(tenant_id=tenant_id, conta_id=conta.id, tipo="reclamacao", criado_em=agora - timedelta(days=1)))
    db.commit()
    return conta


# --- Gestão de chaves ------------------------------------------------------------------
def test_segredo_aparece_uma_vez_e_listagem_nao_expoe(client):
    segredo = _chave(client, ["map:read"])
    assert segredo.startswith("b2bk_")
    listagem = client.get("/api/v1/chaves-api").json()
    assert "segredo" not in listagem[0] and segredo not in str(listagem)


def test_escopo_invalido_e_rejeitado(client):
    assert client.post("/api/v1/chaves-api", json={"nome": "x", "escopos": ["tudo"]}).status_code == 422


def test_usuario_comum_nao_gerencia_chaves(client, criar_usuario_autenticado):
    headers = criar_usuario_autenticado(TENANT_ID, papel="user", email="comum@t.com")
    assert client.get("/api/v1/chaves-api", headers=headers).status_code == 403


# --- Autenticação e autorização -----------------------------------------------------------
def test_sem_chave_ou_chave_invalida_e_401(client):
    sem = client.post("/api/v1/map/churn/predict", json={}, headers={"Authorization": ""})
    assert sem.status_code == 401
    ruim = client.post("/api/v1/map/churn/predict", json={}, headers={"X-API-Key": "b2bk_nao_existe"})
    assert ruim.status_code == 401


def test_jwt_nao_serve_como_chave_de_api(client):
    # O client padrão tem Authorization: Bearer <JWT>; não pode abrir a API de produto.
    assert client.post("/api/v1/map/churn/predict", json={}).status_code == 401


def test_chave_revogada_para_de_funcionar(client):
    segredo = _chave(client, ["map:read"])
    assert client.post("/api/v1/map/churn/predict", json={}, headers={"X-API-Key": segredo}).status_code == 200
    chave_id = client.get("/api/v1/chaves-api").json()[0]["id"]
    client.delete(f"/api/v1/chaves-api/{chave_id}")
    assert client.post("/api/v1/map/churn/predict", json={}, headers={"X-API-Key": segredo}).status_code == 401


def test_escopo_errado_e_403(client):
    segredo = _chave(client, ["map:read"])
    assert client.get("/api/v1/predator/icps", headers={"X-API-Key": segredo}).status_code == 403


def test_modulo_nao_contratado_e_403_mesmo_com_escopo(client, monkeypatch):
    segredo = _chave(client, ["map:read", "predator:read"])
    monkeypatch.setitem(
        app.dependency_overrides, get_plan_limits_provider,
        lambda: StubPlanLimitsProvider(modulos_bloqueados={TENANT_ID: {"map"}}),
    )
    assert client.post("/api/v1/map/churn/predict", json={}, headers={"X-API-Key": segredo}).status_code == 403
    assert client.get("/api/v1/predator/icps", headers={"X-API-Key": segredo}).status_code == 200


def test_licenca_suspensa_bloqueia_a_api(client, db_session):
    segredo = _chave(client, ["map:read"])
    db_session.query(Licenca).filter_by(tenant_id=TENANT_ID).one().status = "suspensa"
    db_session.commit()
    assert client.post("/api/v1/map/churn/predict", json={}, headers={"X-API-Key": segredo}).status_code == 403


def test_rate_limit_por_chave(client):
    segredo = _chave(client, ["predator:read"])
    for _ in range(API_LIMITE_POR_MINUTO):
        assert client.get("/api/v1/predator/icps", headers={"X-API-Key": segredo}).status_code == 200
    assert client.get("/api/v1/predator/icps", headers={"X-API-Key": segredo}).status_code == 429


# --- Isolamento ---------------------------------------------------------------------
def test_chave_do_tenant_a_nunca_ve_dados_do_tenant_b(client, db_session, criar_usuario_autenticado):
    _dados_crm(db_session, TENANT_ID, "Conta do A")
    _dados_crm(db_session, TENANT_B, "Segredo do B")
    headers_b = criar_usuario_autenticado(TENANT_B, papel="admin", email="admin@b.com")
    segredo_a = _chave(client, ["map:read", "predator:read"])
    segredo_b = _chave(client, ["map:read"], headers=headers_b)

    analise_a = client.post("/api/v1/map/analyze", json={"periodo": PERIODO}, headers={"X-API-Key": segredo_a}).json()
    contas_a = client.get("/api/v1/predator/accounts", headers={"X-API-Key": segredo_a}).json()
    analise_b = client.post("/api/v1/map/analyze", json={"periodo": PERIODO}, headers={"X-API-Key": segredo_b}).json()

    assert [c["nome"] for c in analise_a["contas"]] == ["Conta do A"]
    assert "Segredo do B" not in str(analise_a) and "Segredo do B" not in str(contas_a)
    assert all(item["tenant_id"] == TENANT_ID for item in contas_a["items"])
    assert [c["nome"] for c in analise_b["contas"]] == ["Segredo do B"]


def test_payload_nao_consegue_se_passar_por_outro_tenant(client):
    segredo = _chave(client, ["map:read"])
    fonte = {"system": "hubspot", "external_id": "1", "entity": "company"}
    dados = {
        "organizations": [{"id": "hubspot:organization:1", "tenant_id": TENANT_B, "source": fonte, "legal_name": "Externa"}],
        "accounts": [{"id": "hubspot:account:1", "tenant_id": TENANT_B, "source": fonte, "organization_id": "hubspot:organization:1", "lifecycle": "CUSTOMER"}],
    }
    resposta = client.post("/api/v1/map/churn/predict", json={"dados": dados}, headers={"X-API-Key": segredo})
    assert resposta.status_code == 200
    assert resposta.json()["fonte"] == "api_payload"
    assert [p["conta_id"] for p in resposta.json()["previsoes"]] == ["hubspot:account:1"]


# --- Contrato funcional ------------------------------------------------------------------
def test_map_via_payload_canonico_da_o_mesmo_resultado_que_o_crm_interno(client, db_session):
    """CRM externo mandando os mesmos dados no modelo canônico recebe os
    mesmos números que o CRM interno. É o teste de contrato do MAP API."""
    _dados_crm(db_session, TENANT_ID, "Conta 1")
    _dados_crm(db_session, TENANT_ID, "Conta 2")
    adapter = B2BOnCrmAdapter(db_session)
    dados = {
        "organizations": [o.model_dump(mode="json") for o in iterar_todos(adapter.list_organizations, TENANT_ID)],
        "accounts": [a.model_dump(mode="json") for a in iterar_todos(adapter.list_accounts, TENANT_ID)],
        "customers": [c.model_dump(mode="json") for c in iterar_todos(adapter.list_customers, TENANT_ID)],
        "opportunities": [o.model_dump(mode="json") for o in iterar_todos(adapter.list_opportunities, TENANT_ID)],
        "stages": [s.model_dump(mode="json") for s in adapter.list_stages(TENANT_ID)],
        "interactions": [i.model_dump(mode="json") for i in iterar_todos(adapter.list_interactions, TENANT_ID)],
        "cs_metrics": [m.model_dump(mode="json") for m in iterar_todos(adapter.list_cs_metrics, TENANT_ID)],
    }
    segredo = _chave(client, ["map:read"])
    interno = client.post("/api/v1/map/analyze", json={"periodo": PERIODO}, headers={"X-API-Key": segredo}).json()
    externo = client.post("/api/v1/map/analyze", json={"periodo": PERIODO, "dados": dados}, headers={"X-API-Key": segredo}).json()

    assert interno["fonte"] == "b2bon_crm" and externo["fonte"] == "api_payload"
    assert externo["economia"] == interno["economia"]
    assert [(c["score"], c["sinais"]) for c in externo["contas"]] == [(c["score"], c["sinais"]) for c in interno["contas"]]
    assert interno["metodologia"]["risco"] == "RULE_BASED_V1"


def test_metricas_ltv_cac_roi(client, db_session):
    _dados_crm(db_session, TENANT_ID, "Conta 1")
    segredo = _chave(client, ["map:read"])
    ltv = client.post("/api/v1/map/ltv", json={"periodo": PERIODO}, headers={"X-API-Key": segredo}).json()
    cac = client.post("/api/v1/map/cac", json={"periodo": PERIODO}, headers={"X-API-Key": segredo}).json()
    assert ltv["valor"] == 5000.0
    assert cac["valor"] is None  # sem custo de aquisição lançado: não inventa


def test_periodo_invalido_e_422(client):
    segredo = _chave(client, ["map:read"])
    assert client.post("/api/v1/map/ltv", json={"periodo": "2026-13"}, headers={"X-API-Key": segredo}).status_code == 422


# --- Idempotência ----------------------------------------------------------------------
@pytest.fixture()
def icp_com_candidatos(criar_icp, fake_account_data):
    fake_account_data.candidatos = [
        ContaCandidata(cnpj=f"1234567800019{i}", razao_social=f"Empresa {i}", cnae_principal="6201500", porte="PEQUENO",
                       uf="SP", situacao_cadastral="ATIVA", fonte="receita_federal_cnpj")
        for i in range(3)
    ]
    return criar_icp()


def test_idempotency_key_reexecucao_devolve_a_mesma_resposta(client, db_session, icp_com_candidatos):
    segredo = _chave(client, ["predator:write"])
    headers = {"X-API-Key": segredo, "Idempotency-Key": "lote-000001"}
    corpo = {"icp_id": icp_com_candidatos["id"], "quantidade": 3}

    primeira = client.post("/api/v1/predator/lists/generate", json=corpo, headers=headers)
    segunda = client.post("/api/v1/predator/lists/generate", json=corpo, headers=headers)

    assert primeira.status_code == segunda.status_code == 201
    assert primeira.json() == segunda.json() and len(primeira.json()["contas"]) == 3
    assert segunda.headers.get("Idempotent-Replayed") == "true"
    assert db_session.query(Conta).filter_by(tenant_id=TENANT_ID).count() == 3


def test_idempotency_key_reusada_com_outro_corpo_e_conflito(client, icp_com_candidatos):
    segredo = _chave(client, ["predator:write"])
    headers = {"X-API-Key": segredo, "Idempotency-Key": "lote-000002"}
    client.post("/api/v1/predator/lists/generate", json={"icp_id": icp_com_candidatos["id"], "quantidade": 1}, headers=headers)
    conflito = client.post("/api/v1/predator/lists/generate", json={"icp_id": icp_com_candidatos["id"], "quantidade": 2}, headers=headers)
    assert conflito.status_code == 409


def test_escrita_sem_idempotency_key_e_rejeitada(client, icp_com_candidatos):
    segredo = _chave(client, ["predator:write"])
    resposta = client.post("/api/v1/predator/lists/generate", json={"icp_id": icp_com_candidatos["id"], "quantidade": 1}, headers={"X-API-Key": segredo})
    assert resposta.status_code == 422


# --- Observabilidade -------------------------------------------------------------------
def test_correlation_id_e_devolvido_e_propagado_ao_evento(client, db_session):
    conta = Conta(tenant_id=TENANT_ID, nome="C", status="prospectada")
    db_session.add(conta)
    db_session.commit()
    decisor = Decisor(tenant_id=TENANT_ID, conta_id=conta.id, nome="D")
    db_session.add(decisor)
    db_session.commit()

    resposta = client.post(
        "/api/v1/crm/negocios", json={"conta_id": conta.id, "decisor_id": decisor.id, "nome": "N", "valor": 1},
        headers={"X-Request-ID": "req-teste-123456"},
    )
    assert resposta.headers["X-Request-ID"] == "req-teste-123456"
    evento = db_session.query(EventoDominio).filter_by(tipo="OpportunityCreated").one()
    assert evento.correlation_id == "req-teste-123456"


def test_correlation_id_invalido_e_substituido(client):
    resposta = client.get("/api/v1/planos", headers={"X-Request-ID": "x y<script>"})
    assert resposta.headers["X-Request-ID"] != "x y<script>" and len(resposta.headers["X-Request-ID"]) == 32


# --- Contrato OpenAPI ------------------------------------------------------------------
def test_contrato_openapi_das_apis_de_produto(client):
    esquema = client.get("/openapi.json").json()
    caminhos = esquema["paths"]
    esperados = {
        ("/api/v1/map/analyze", "post"), ("/api/v1/map/churn/predict", "post"), ("/api/v1/map/customer-score", "post"),
        ("/api/v1/map/ltv", "post"), ("/api/v1/map/cac", "post"), ("/api/v1/map/roi", "post"),
        ("/api/v1/predator/icps", "get"), ("/api/v1/predator/accounts", "get"),
        ("/api/v1/predator/company/enrich", "post"), ("/api/v1/predator/lists/generate", "post"),
    }
    for caminho, metodo in esperados:
        assert metodo in caminhos.get(caminho, {}), (caminho, metodo)
    analyze = caminhos["/api/v1/map/analyze"]["post"]
    assert "MapAnaliseResponse" in str(analyze["responses"]["200"])
    parametros = {p["name"] for p in caminhos["/api/v1/predator/lists/generate"]["post"]["parameters"]}
    assert {"Idempotency-Key", "X-API-Key"} <= parametros
