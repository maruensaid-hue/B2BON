"""Conector Pipedrive (Fase 13, conector 3/4). GATE: contrato do adapter,
auth, retry, sync incremental (/recents), isolamento e paridade do MAP.

O servidor falso responde no formato documentado da API v1
(`success`/`data`/`additional_data.pagination`, referências como objeto
`{"value": id}`, datas 'AAAA-MM-DD HH:MM:SS', 401 `unauthorized access`).
"""

import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from app.contexts.integrations import sync
from app.contexts.integrations.adapters import http_base
from app.contexts.integrations.adapters.pipedrive import PipedriveAdapter, validar
from app.contexts.integrations.contract import iterar_todos
from app.contexts.shared.canonical.commercial import AccountLifecycle, ActivityKind, OpportunityStatus
from app.core.config import settings
from app.models.conexao_integracao import ConexaoIntegracao
from tests.conectores_crm import coletar, verificar_contrato

TENANT = "tenant-teste"
TOKEN = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
CREDENCIAIS = {"api_token": TOKEN}
CAMPO_CNPJ = "4f1c2d3e4b5a69788796a5b4c3d2e1f0a9b8c7d6"
H = "/api/v1/hub-integracoes"


def _t(**campos) -> dict:
    return {"add_time": "2025-06-01 09:00:00", "update_time": "2026-01-10 12:00:00", **campos}


DADOS = {
    "organizations": [
        _t(id=1, name="ACME Ltda", owner_id={"id": 11, "name": "Vendedor"}, won_deals_count=1, address_admin_area_level_1="SP",
           **{CAMPO_CNPJ: "11.222.333/0001-81"}),
        _t(id=2, name="Beta SA", owner_id={"id": 11}, won_deals_count=0, update_time="2026-03-01 00:00:00"),
        _t(id=3, name="Gama ME", owner_id=12, won_deals_count=2),
    ],
    "persons": [
        _t(id=21, name="Ana Souza", org_id={"value": 1, "name": "ACME Ltda"}, job_title="CFO",
           email=[{"label": "work", "value": "ana@acme.com.br", "primary": True}], phone=[{"value": "", "primary": True}],
           marketing_status="unsubscribed"),
        _t(id=22, name="Solto", org_id=None, email=[], phone=[], marketing_status="subscribed"),
    ],
    "pipelines": [{"id": 1, "name": "Pipeline"}],
    "stages": [{"id": 1, "name": "Qualificado", "pipeline_id": 1, "order_nr": 1}, {"id": 2, "name": "Proposta", "pipeline_id": 1, "order_nr": 2}],
    "deals": [
        _t(id=31, title="Licenças 2026", org_id={"value": 1}, user_id={"id": 11}, value=5000, currency="BRL", status="won",
           won_time="2026-01-05 10:00:00", pipeline_id=1, stage_id=2, probability=None),
        _t(id=32, title="Expansão", org_id={"value": 1}, user_id={"id": 11}, value=1200.5, currency="USD", status="open",
           pipeline_id=1, stage_id=1, probability=20),
        _t(id=33, title="Piloto", org_id={"value": 2}, user_id={"id": 11}, value=0, currency="BRL", status="lost",
           lost_time="2026-02-01 08:00:00", lost_reason="Preço", pipeline_id=1, stage_id=1),
        _t(id=34, title="Sem organização", org_id=None, value=10, currency="BRL", status="open", pipeline_id=1, stage_id=1),
        _t(id=35, title="Canal", org_id={"value": 3}, value=800, currency="BRL", status="won", won_time="2025-11-20 09:00:00", pipeline_id=1, stage_id=2),
        _t(id=36, title="Canal antigo", org_id={"value": 3}, value=300, currency="BRL", status="won", won_time="2025-12-20 09:00:00", pipeline_id=1, stage_id=2),
    ],
    "activities": [
        _t(id=41, type="call", subject="Ligação de follow-up", org_id=1, deal_id=31, done=True, marked_as_done_time="2026-01-08 10:00:00"),
        _t(id=42, type="meeting", subject="Reunião trimestral", org_id=3, deal_id=None, done=True, marked_as_done_time="2026-01-09 10:00:00"),
        _t(id=43, type="task", subject="Enviar material", org_id=2, deal_id=None, done=False),
        _t(id=44, type="lunch", subject="Almoço", org_id=None, deal_id=None, done=True),
    ],
    "products": [{"id": 51, "name": "Plataforma", "category": None, "description": None, "active_flag": True}],
}


class FakePipedrive:
    def __init__(self, tamanho_pagina: int = 2) -> None:
        self.tamanho = tamanho_pagina
        self.token_valido = TOKEN
        self.falhas_429 = 0
        self.requisicoes: list[httpx.Request] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._tratar)

    def _pagina(self, registros: list, inicio: int, limite: int) -> dict:
        limite = min(limite, self.tamanho)
        fatia = registros[inicio:inicio + limite]
        mais = inicio + limite < len(registros)
        paginacao = {"start": inicio, "limit": limite, "more_items_in_collection": mais}
        if mais:
            paginacao["next_start"] = inicio + limite
        return {"success": True, "data": fatia or None, "additional_data": {"pagination": paginacao}}

    def _tratar(self, request: httpx.Request) -> httpx.Response:
        self.requisicoes.append(request)
        if "api_token" in str(request.url):
            return httpx.Response(400, json={"success": False, "error": "token na URL"})
        if request.headers.get("x-api-token") != self.token_valido:
            return httpx.Response(401, json={"success": False, "error": "unauthorized access", "errorCode": 401})
        if self.falhas_429:
            self.falhas_429 -= 1
            return httpx.Response(429, json={"success": False, "error": "Request over limit"})
        recurso = request.url.path.removeprefix("/v1/")
        params = request.url.params
        inicio, limite = int(params.get("start", 0)), int(params.get("limit", 100))
        if recurso == "recents":
            objeto = params["items"]
            limiar = datetime.fromisoformat(params["since_timestamp"].replace(" ", "T"))
            plural = {"organization": "organizations", "person": "persons", "deal": "deals"}[objeto]
            itens = [{"item": objeto, "id": r["id"], "data": r} for r in DADOS[plural]
                     if datetime.fromisoformat(r["update_time"].replace(" ", "T")) > limiar]
            return httpx.Response(200, json=self._pagina(itens, inicio, limite))
        registros = DADOS[recurso]
        if recurso == "deals" and params.get("status"):
            registros = [r for r in registros if r["status"] == params["status"]]
        if recurso == "activities" and params.get("done") == "1":
            registros = [r for r in registros if r["done"]]
        return httpx.Response(200, json=self._pagina(registros, inicio, limite))


@pytest.fixture()
def fake_pd(monkeypatch) -> FakePipedrive:
    fake = FakePipedrive()
    monkeypatch.setattr(http_base, "TRANSPORTE_PADRAO", fake.transport())
    return fake


def _adapter(fake: FakePipedrive) -> PipedriveAdapter:
    return PipedriveAdapter(TENANT, CREDENCIAIS, {"campo_cnpj": CAMPO_CNPJ}, transport=fake.transport())


@pytest.mark.parametrize("credenciais,config", [
    ({}, {}), ({"api_token": "curto"}, {}), ({"api_token": TOKEN + "&x=1"}, {}),
    ({**CREDENCIAIS, "company_domain": "evil"}, {}), (CREDENCIAIS, {"campo_cnpj": "X; DROP"}),
])
def test_credenciais_e_configuracao_invalidas_sao_recusadas(credenciais, config):
    with pytest.raises(ValueError):
        validar(credenciais, config)


def test_contrato_token_so_no_header_e_paginacao_ate_o_fim():
    fake = FakePipedrive()
    dados = verificar_contrato(_adapter(fake), TENANT, "pipedrive")
    assert len(dados["accounts"]) == 3 and any(r.url.params.get("start") == "2" for r in fake.requisicoes)
    assert len(dados["opportunities"]) == 5  # sem organização não é atribuído
    assert {r.url.host for r in fake.requisicoes} == {"api.pipedrive.com"}
    assert not any(TOKEN in str(r.url) for r in fake.requisicoes)


def test_mapeamento_de_organizacoes_pessoas_negocios_e_atividades():
    dados = coletar(_adapter(FakePipedrive()), TENANT)
    orgs = {o.source.external_id: o for o in dados["organizations"]}
    assert (orgs["1"].legal_name, orgs["1"].tax_id, orgs["1"].region, orgs["1"].domain) == ("ACME Ltda", "11222333000181", "SP", None)
    contas = {a.source.external_id: a for a in dados["accounts"]}
    assert {k: a.lifecycle for k, a in contas.items()} == {"1": AccountLifecycle.CUSTOMER, "2": AccountLifecycle.PROSPECT, "3": AccountLifecycle.CUSTOMER}
    assert (contas["1"].owner_user_id, contas["3"].owner_user_id) == ("11", "12")
    assert {c.account_id: c.customer_since for c in dados["customers"]} == {
        "pipedrive:account:1": datetime(2026, 1, 5, 10, tzinfo=UTC), "pipedrive:account:3": datetime(2025, 11, 20, 9, tzinfo=UTC)}

    pessoas = {p.source.external_id: p for p in dados["people"]}
    assert (pessoas["21"].email, pessoas["21"].phone, pessoas["21"].job_title) == ("ana@acme.com.br", None, "CFO")
    assert pessoas["21"].suppressed_at is not None and pessoas["22"].suppressed_at is None
    assert [c.account_id for c in dados["contacts"]] == ["pipedrive:account:1"]

    ops = {o.name: o for o in dados["opportunities"]}
    assert ops["Licenças 2026"].status == OpportunityStatus.WON and ops["Licenças 2026"].closed_at == datetime(2026, 1, 5, 10, tzinfo=UTC)
    assert ops["Expansão"].amount.amount == Decimal("1200.5") and ops["Expansão"].amount.currency == "USD" and ops["Expansão"].probability == 20
    assert (ops["Piloto"].status, ops["Piloto"].lost_reason, ops["Piloto"].amount.amount) == (OpportunityStatus.LOST, "Preço", Decimal("0"))
    assert ops["Expansão"].closed_at is None

    atividades = {a.description: a for a in dados["activities"]}
    assert atividades["Ligação de follow-up"].kind == ActivityKind.CALL and atividades["Ligação de follow-up"].opportunity_id == "pipedrive:opportunity:31"
    assert atividades["Almoço"].kind == ActivityKind.OTHER and atividades["Almoço"].source_type == "lunch"
    # só concluídas com organização viram interação de contato
    assert sorted(i.description for i in dados["interactions"]) == ["Ligação de follow-up", "Reunião trimestral"]
    assert [o.name for o in dados["offers"]] == ["Plataforma"]


def test_interacoes_por_conta_lidas_uma_vez_e_cursor_forjado_recusado():
    fake = FakePipedrive()
    adapter = _adapter(fake)
    assert [i.description for i in iterar_todos(adapter.list_interactions, TENANT, account_id="pipedrive:account:3")] == ["Reunião trimestral"]
    antes = len(fake.requisicoes)
    adapter.list_interactions(TENANT, account_id="pipedrive:account:1")
    assert len(fake.requisicoes) == antes
    with pytest.raises(ValueError):
        adapter.list_accounts(TENANT, cursor="1&api_token=x")


def test_updated_since_usa_recents():
    fake = FakePipedrive()
    pagina = _adapter(fake).list_accounts(TENANT, updated_since=datetime(2026, 2, 1, tzinfo=UTC))
    params = fake.requisicoes[-1].url.params
    assert fake.requisicoes[-1].url.path == "/v1/recents" and (params["items"], params["since_timestamp"]) == ("organization", "2026-02-01 00:00:00")
    assert [a.source.external_id for a in pagina.items] == ["2"]


def _conexao(db, token=TOKEN) -> ConexaoIntegracao:
    conexao = ConexaoIntegracao(tenant_id=TENANT, sistema="pipedrive", nome="PD", status="ativa",
                                configuracao={}, credenciais=json.dumps({"api_token": token}))
    db.add(conexao)
    db.commit()
    return conexao


def test_429_retentado_incremental_e_401_sem_retry(db_session, fake_pd):
    conexao = _conexao(db_session)
    fake_pd.falhas_429 = 2
    primeira = sync.sincronizar(db_session, conexao, "opportunities", dormir=lambda s: None)
    assert (primeira.status, primeira.itens_lidos, primeira.paginas) == ("sucesso", 5, 3)
    sync.sincronizar(db_session, conexao, "opportunities", dormir=lambda s: None)
    assert fake_pd.requisicoes[-1].url.path == "/v1/recents"

    revogado = "f" * 40
    ruim = _conexao(db_session, revogado)
    antes = len(fake_pd.requisicoes)
    execucao = sync.sincronizar(db_session, ruim, "accounts", dormir=lambda s: None)
    assert execucao.status == "falha" and len(fake_pd.requisicoes) == antes + 1 and ruim.status == "erro"
    assert revogado not in ruim.ultimo_erro


def test_hub_e_map_via_conexao_pipedrive(client, fake_pd, monkeypatch):
    conector = next(c for c in client.get(f"{H}/conectores").json() if c["sistema"] == "pipedrive")
    assert (conector["status"], conector["conectavel"]) == ("BETA", False)
    monkeypatch.setattr(settings, "conectores_crm_habilitados", "pipedrive")
    resposta = client.post(f"{H}/conexoes", json={"sistema": "pipedrive", "nome": "PD", "credenciais": CREDENCIAIS})
    assert resposta.status_code == 201 and TOKEN not in resposta.text
    conexao = resposta.json()

    dados = coletar(PipedriveAdapter(TENANT, CREDENCIAIS, transport=fake_pd.transport()), TENANT)
    payload = {chave: [i.model_dump(mode="json") for i in dados[chave]]
               for chave in ("organizations", "accounts", "customers", "opportunities", "stages", "interactions", "cs_metrics")}
    segredo = client.post("/api/v1/chaves-api", json={"nome": "pd", "escopos": ["map:read"]}).json()["segredo"]
    via_conexao = client.post("/api/v1/map/analyze", json={"periodo": "2026-01", "conexao_id": conexao["id"]}, headers={"X-API-Key": segredo}).json()
    via_payload = client.post("/api/v1/map/analyze", json={"periodo": "2026-01", "dados": payload}, headers={"X-API-Key": segredo}).json()
    assert via_conexao["fonte"] == "conexao:pipedrive" and via_conexao["economia"] == via_payload["economia"]
    assert [(c["conta_id"], c["score"]) for c in via_conexao["contas"]] == [(c["conta_id"], c["score"]) for c in via_payload["contas"]]
