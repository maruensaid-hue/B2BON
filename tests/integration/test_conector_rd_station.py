"""Conector RD Station CRM (Fase 13, conector 4/4). GATE: contrato do
adapter, token fora de logs/erros, retry, isolamento e paridade do MAP.

O servidor falso responde no formato documentado da API v1
(`{"organizations": [...], "has_more": bool}`, `deal_pipelines` como lista
com `deal_stages`, token na query, 401 com `{"errors": ...}`).
"""

import json
import logging
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from app.contexts.integrations import sync
from app.contexts.integrations.adapters import http_base
from app.contexts.integrations.adapters.rd_station import RdStationCrmAdapter, validar
from app.contexts.integrations.contract import iterar_todos
from app.contexts.shared.canonical.commercial import AccountLifecycle, ActivityKind, OpportunityStatus
from app.core.config import settings
from app.models.conexao_integracao import ConexaoIntegracao
from tests.conectores_crm import coletar, verificar_contrato

TENANT = "tenant-teste"
TOKEN = "rdcrm-0123456789abcdef"
CREDENCIAIS = {"token": TOKEN}
H = "/api/v1/hub-integracoes"
ORG_A, ORG_B, ORG_C = "5f00000000000000000000a1", "5f00000000000000000000b2", "5f00000000000000000000c3"


def _t(**campos) -> dict:
    return {"created_at": "2025-06-01T09:00:00.000-03:00", "updated_at": "2026-01-10T12:00:00.000-03:00", **campos}


DADOS = {
    "organizations": [
        _t(id=ORG_A, name="ACME Ltda", url="https://www.acme.com.br/contato", user={"id": "u1", "name": "Vendedor"},
           organization_segments=[{"id": "s1", "name": "Indústria"}],
           custom_fields=[{"custom_field_id": "cf_cnpj", "value": "11.222.333/0001-81"}]),
        _t(id=ORG_B, name="Beta SA", url=None, user={"id": "u1"}, organization_segments=[], custom_fields=[]),
        _t(id=ORG_C, name="Gama ME", url="gama.com", user=None),
    ],
    "contacts": [
        _t(id="c1", name="Ana Souza", title="CFO", organization_id=ORG_A, emails=[{"email": "ana@acme.com.br"}], phones=[{"phone": "11999990000"}]),
        _t(id="c2", name="Solto", title=None, organization_id=None, emails=[], phones=[]),
    ],
    "deals": [
        _t(id="d1", name="Licenças 2026", amount_total=5000.0, win=True, closed_at="2026-01-05T10:00:00.000-03:00",
           organization={"id": ORG_A, "name": "ACME Ltda"}, deal_stage={"id": "st2", "name": "Proposta"}, user={"id": "u1"}),
        _t(id="d2", name="Expansão", amount_total=1200.5, win=None, closed_at=None, organization={"id": ORG_A},
           deal_stage={"id": "st1", "name": "Qualificação"}, user={"id": "u1"}),
        _t(id="d3", name="Piloto", amount_total=0, win=False, closed_at="2026-02-01T08:00:00.000-03:00", organization={"id": ORG_B},
           deal_stage={"id": "st1"}, deal_lost_reason={"id": "l1", "name": "Preço"}),
        _t(id="d4", name="Sem organização", amount_total=10, win=None, organization=None, deal_stage={"id": "st1"}),
        _t(id="d5", name="Canal", amount_total=800, win=True, closed_at="2025-11-20T09:00:00.000-03:00", organization={"id": ORG_C},
           deal_stage={"id": "st2"}),
    ],
    "tasks": [
        _t(id="t1", subject="Ligação de follow-up", type="call", deal_id="d1", done=True, done_date="2026-01-08T10:00:00.000-03:00", users=[{"id": "u1"}]),
        _t(id="t2", subject="Visita técnica", type="visit", deal_id="d5", done=True, done_date="2026-01-09T10:00:00.000-03:00"),
        _t(id="t3", subject="Enviar material", type="email", deal_id="d3", done=False),
        _t(id="t4", subject="WhatsApp", type="whatsapp", deal_id=None, done=True),
    ],
    "products": [{"id": "p1", "name": "Plataforma", "description": "SaaS", "visible": True}],
}
PIPELINES = [{"id": "pl1", "name": "Funil padrão", "deal_stages": [
    {"id": "st1", "name": "Qualificação", "nickname": "QL"}, {"id": "st2", "name": "Proposta", "nickname": "PR"}]}]


class FakeRdStation:
    def __init__(self, tamanho_pagina: int = 2) -> None:
        self.tamanho = tamanho_pagina
        self.falhas_429 = 0
        self.requisicoes: list[httpx.Request] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._tratar)

    def _tratar(self, request: httpx.Request) -> httpx.Response:
        self.requisicoes.append(request)
        params = request.url.params
        if params.get("token") != TOKEN:
            return httpx.Response(401, json={"errors": "Unauthorized"})
        if self.falhas_429:
            self.falhas_429 -= 1
            return httpx.Response(429, json={"errors": "Too many requests"})
        recurso = request.url.path.removeprefix("/api/v1/")
        if recurso == "deal_pipelines":
            return httpx.Response(200, json=PIPELINES)
        registros = DADOS[recurso]
        if recurso == "tasks" and params.get("done") == "true":
            registros = [r for r in registros if r["done"]]
        pagina = int(params.get("page", 1))
        limite = min(int(params.get("limit", 20)), self.tamanho)
        inicio = (pagina - 1) * limite
        return httpx.Response(200, json={recurso: registros[inicio:inicio + limite], "total": len(registros),
                                         "has_more": inicio + limite < len(registros)})


@pytest.fixture()
def fake_rd(monkeypatch) -> FakeRdStation:
    fake = FakeRdStation()
    monkeypatch.setattr(http_base, "TRANSPORTE_PADRAO", fake.transport())
    return fake


def _adapter(fake: FakeRdStation) -> RdStationCrmAdapter:
    return RdStationCrmAdapter(TENANT, CREDENCIAIS, {"campo_cnpj": "cf_cnpj"}, transport=fake.transport())


@pytest.mark.parametrize("credenciais,config", [
    ({}, {}), ({"token": "curto"}, {}), ({"token": TOKEN + "&x=1"}, {}), ({**CREDENCIAIS, "url": "https://evil"}, {}),
    (CREDENCIAIS, {"campo_cnpj": "a b"}), (CREDENCIAIS, {"moeda": "brl"}),
])
def test_credenciais_e_configuracao_invalidas_sao_recusadas(credenciais, config):
    with pytest.raises(ValueError):
        validar(credenciais, config)


def test_contrato_paginacao_e_isolamento_e_sem_incremental():
    fake = FakeRdStation()
    adapter = _adapter(fake)
    dados = verificar_contrato(adapter, TENANT, "rd_station")
    assert not adapter.capabilities().incremental_sync  # a v1 não filtra por alteração: não fingimos
    assert len(dados["accounts"]) == 3 and any(r.url.params.get("page") == "2" for r in fake.requisicoes)
    assert len(dados["opportunities"]) == 4
    assert {r.url.host for r in fake.requisicoes} == {"crm.rdstation.com"}


def test_mapeamento_de_organizacoes_contatos_negociacoes_e_tarefas():
    dados = coletar(_adapter(FakeRdStation()), TENANT)
    orgs = {o.source.external_id: o for o in dados["organizations"]}
    assert (orgs[ORG_A].domain, orgs[ORG_A].tax_id, orgs[ORG_A].industry) == ("acme.com.br", "11222333000181", "Indústria")
    assert orgs[ORG_B].domain is None and orgs[ORG_C].domain == "gama.com"
    assert {a.source.external_id: a.lifecycle for a in dados["accounts"]} == {
        ORG_A: AccountLifecycle.CUSTOMER, ORG_B: AccountLifecycle.PROSPECT, ORG_C: AccountLifecycle.CUSTOMER}
    assert {c.account_id: c.customer_since for c in dados["customers"]} == {
        f"rd_station:account:{ORG_A}": datetime(2026, 1, 5, 13, tzinfo=UTC),
        f"rd_station:account:{ORG_C}": datetime(2025, 11, 20, 12, tzinfo=UTC)}

    ana = next(p for p in dados["people"] if p.full_name == "Ana Souza")
    assert (ana.email, ana.phone, ana.job_title, ana.suppressed_at) == ("ana@acme.com.br", "11999990000", "CFO", None)
    assert [c.account_id for c in dados["contacts"]] == [f"rd_station:account:{ORG_A}"]

    ops = {o.name: o for o in dados["opportunities"]}
    assert ops["Licenças 2026"].status == OpportunityStatus.WON and ops["Licenças 2026"].pipeline_id == "rd_station:pipeline:pl1"
    assert ops["Expansão"].status == OpportunityStatus.OPEN and ops["Expansão"].closed_at is None
    assert ops["Expansão"].amount.amount == Decimal("1200.5") and ops["Expansão"].amount.currency == "BRL"
    assert (ops["Piloto"].status, ops["Piloto"].lost_reason) == (OpportunityStatus.LOST, "Preço")

    atividades = {a.description: a for a in dados["activities"]}
    assert atividades["Ligação de follow-up"].kind == ActivityKind.CALL
    assert atividades["Ligação de follow-up"].account_id == f"rd_station:account:{ORG_A}"
    assert atividades["Visita técnica"].kind == ActivityKind.MEETING
    assert atividades["WhatsApp"].kind == ActivityKind.OTHER and atividades["WhatsApp"].source_type == "whatsapp"
    assert sorted(i.description for i in dados["interactions"]) == ["Ligação de follow-up", "Visita técnica"]
    assert [o.name for o in dados["offers"]] == ["Plataforma"]


def test_interacoes_por_conta_lidas_uma_vez_e_cursor_forjado():
    fake = FakeRdStation()
    adapter = _adapter(fake)
    itens = iterar_todos(adapter.list_interactions, TENANT, account_id=f"rd_station:account:{ORG_C}")
    assert [i.description for i in itens] == ["Visita técnica"]
    antes = len(fake.requisicoes)
    adapter.list_interactions(TENANT, account_id=f"rd_station:account:{ORG_A}")
    assert len(fake.requisicoes) == antes
    with pytest.raises(ValueError):
        adapter.list_accounts(TENANT, cursor="2&token=outro")


def _conexao(db, token=TOKEN) -> ConexaoIntegracao:
    conexao = ConexaoIntegracao(tenant_id=TENANT, sistema="rd_station", nome="RD", status="ativa",
                                configuracao={}, credenciais=json.dumps({"token": token}))
    db.add(conexao)
    db.commit()
    return conexao


def test_token_da_query_nunca_aparece_em_log_nem_em_erro(db_session, fake_rd, caplog):
    conexao = _conexao(db_session)
    fake_rd.falhas_429 = 1
    with caplog.at_level(logging.INFO, logger="httpx"):
        execucao = sync.sincronizar(db_session, conexao, "accounts", dormir=lambda s: None)
    assert (execucao.status, execucao.itens_lidos, execucao.incremental_desde) == ("sucesso", 3, None)
    assert "token=***" in caplog.text and TOKEN not in caplog.text

    segunda = sync.sincronizar(db_session, conexao, "accounts", dormir=lambda s: None)
    assert segunda.incremental_desde is None  # sem incremental declarado: relê tudo

    revogado = "rdcrm-revogado-000000000"
    ruim = _conexao(db_session, revogado)
    antes = len(fake_rd.requisicoes)
    falha = sync.sincronizar(db_session, ruim, "accounts", dormir=lambda s: None)
    assert falha.status == "falha" and len(fake_rd.requisicoes) == antes + 1 and ruim.status == "erro"
    assert revogado not in falha.erro and revogado not in (ruim.ultimo_erro or "")


def test_erro_de_transporte_com_url_tem_o_token_mascarado(db_session, monkeypatch):
    def quebrar(request):
        raise httpx.ConnectError(f"falhou ao conectar em {request.url}")

    monkeypatch.setattr(http_base, "TRANSPORTE_PADRAO", httpx.MockTransport(quebrar))
    execucao = sync.sincronizar(db_session, _conexao(db_session), "accounts", dormir=lambda s: None)
    assert execucao.status == "falha" and "token=***" in execucao.erro and TOKEN not in execucao.erro


def test_hub_e_map_via_conexao_rd_station(client, fake_rd, monkeypatch):
    conector = next(c for c in client.get(f"{H}/conectores").json() if c["sistema"] == "rd_station")
    assert (conector["status"], conector["conectavel"]) == ("BETA", False)
    monkeypatch.setattr(settings, "conectores_crm_habilitados", "rd_station")
    resposta = client.post(f"{H}/conexoes", json={"sistema": "rd_station", "nome": "RD", "credenciais": CREDENCIAIS})
    assert resposta.status_code == 201 and TOKEN not in resposta.text
    conexao = resposta.json()

    dados = coletar(RdStationCrmAdapter(TENANT, CREDENCIAIS, transport=fake_rd.transport()), TENANT)
    payload = {chave: [i.model_dump(mode="json") for i in dados[chave]]
               for chave in ("organizations", "accounts", "customers", "opportunities", "stages", "interactions", "cs_metrics")}
    segredo = client.post("/api/v1/chaves-api", json={"nome": "rd", "escopos": ["map:read"]}).json()["segredo"]
    via_conexao = client.post("/api/v1/map/analyze", json={"periodo": "2026-01", "conexao_id": conexao["id"]}, headers={"X-API-Key": segredo}).json()
    via_payload = client.post("/api/v1/map/analyze", json={"periodo": "2026-01", "dados": payload}, headers={"X-API-Key": segredo}).json()
    assert via_conexao["fonte"] == "conexao:rd_station" and via_conexao["economia"] == via_payload["economia"]
    assert [(c["conta_id"], c["score"]) for c in via_conexao["contas"]] == [(c["conta_id"], c["score"]) for c in via_payload["contas"]]
