"""Conector HubSpot (Fase 13, conector 2/4). GATE: contrato do adapter,
auth, retry, sync incremental (Search API), isolamento e paridade do MAP.

O servidor falso responde no formato documentado da CRM API v3
(`results` + `paging.next.after`, propriedades como texto, `associations`
na listagem, Search API por POST, Associations API v4 em lote, erro 401
`EXPIRED_AUTHENTICATION`).
"""

import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from app.contexts.integrations import sync
from app.contexts.integrations.adapters import http_base
from app.contexts.integrations.adapters.hubspot import HubSpotAdapter, validar
from app.contexts.integrations.contract import ErroCredencial, iterar_todos
from app.contexts.shared.canonical.commercial import AccountLifecycle, ActivityKind, OpportunityStatus, StageType
from app.core.config import settings
from app.models.conexao_integracao import ConexaoIntegracao
from tests.conectores_crm import coletar, verificar_contrato

TENANT = "tenant-teste"
CREDENCIAIS = {"access_token": "pat-valido"}
H = "/api/v1/hub-integracoes"
MOD = "2026-01-10T12:00:00.000Z"


def _o(id_: str, atualizado: str = MOD, associacoes: dict | None = None, **props) -> dict:
    registro = {"id": id_, "properties": {k: v for k, v in props.items()}, "createdAt": "2025-06-01T09:00:00.000Z",
                "updatedAt": atualizado, "archived": False}
    registro["properties"].setdefault("hs_lastmodifieddate", atualizado)
    registro["properties"].setdefault("lastmodifieddate", atualizado)
    if associacoes:
        registro["associations"] = {tipo: {"results": [{"id": i, "type": f"x_to_{tipo}"} for i in ids]} for tipo, ids in associacoes.items()}
    return registro


OBJETOS = {
    "companies": [
        _o("101", name="ACME Ltda", domain="www.acme.com.br", industry="MANUFACTURING", numberofemployees="250", state="SP",
           lifecyclestage="customer", hubspot_owner_id="9001", hs_lifecyclestage_customer_date="2026-01-05T00:00:00Z",
           cnpj="11.222.333/0001-81"),
        _o("102", atualizado="2026-03-01T00:00:00.000Z", name="Beta SA", domain=None, lifecyclestage="salesqualifiedlead"),
        _o("103", name="Gama ME", domain="gama.com", lifecyclestage="customer", hs_lifecyclestage_customer_date=None),
    ],
    "contacts": [
        _o("201", firstname="Ana", lastname="Souza", email="ana@acme.com.br", jobtitle="CFO", associatedcompanyid="101",
           hs_email_optout="true"),
        _o("202", firstname=None, lastname=None, email="solto@x.com", associatedcompanyid=None, hs_email_optout="false"),
    ],
    "deals": [
        _o("301", dealname="Licenças 2026", amount="5000", dealstage="closedwon", pipeline="default", closedate="2026-01-05T00:00:00Z",
           hs_is_closed="true", hs_is_closed_won="true", hs_deal_stage_probability="1.0", deal_currency_code="BRL", hubspot_owner_id="9001"),
        _o("302", dealname="Expansão", amount="1200.50", dealstage="appointmentscheduled", pipeline="default", closedate="2026-12-01T00:00:00Z",
           hs_is_closed="false", hs_is_closed_won="false", hs_deal_stage_probability="0.2", deal_currency_code=None),
        _o("303", dealname="Piloto", amount="", dealstage="closedlost", pipeline="default", closedate="2026-02-01T00:00:00Z",
           hs_is_closed="true", hs_is_closed_won="false", hs_deal_stage_probability="0.0"),
        _o("304", dealname="Sem empresa", amount="10", dealstage="appointmentscheduled", pipeline="default",
           hs_is_closed="false", hs_is_closed_won="false"),
    ],
    "calls": [_o("401", associacoes={"companies": ["101"], "deals": ["301"]}, hs_call_title="Ligação de follow-up", hs_timestamp="2026-01-08T10:00:00Z")],
    "emails": [],
    "meetings": [_o("402", associacoes={"companies": ["103"]}, hs_meeting_title="Reunião trimestral", hs_timestamp="2026-01-09T10:00:00Z")],
    "tasks": [_o("403", hs_task_subject="Tarefa solta")],
    "notes": [_o("404", associacoes={"companies": ["102"]}, hs_note_body="<p>Pediu <b>proposta</b></p>")],
    "products": [_o("501", name="Plataforma", description="SaaS")],
}
DEAL_EMPRESA = {"301": "101", "302": "101", "303": "102"}
PIPELINES = {"results": [{"id": "default", "label": "Sales Pipeline", "displayOrder": 0, "stages": [
    {"id": "appointmentscheduled", "label": "Appointment Scheduled", "displayOrder": 0, "metadata": {"isClosed": "false", "probability": "0.2"}},
    {"id": "closedwon", "label": "Closed Won", "displayOrder": 5, "metadata": {"isClosed": "true", "probability": "1.0"}},
    {"id": "closedlost", "label": "Closed Lost", "displayOrder": 6, "metadata": {"isClosed": "true", "probability": "0.0"}},
]}]}


def _ms(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp() * 1000)


class FakeHubSpot:
    def __init__(self, tamanho_pagina: int = 2) -> None:
        self.tamanho = tamanho_pagina
        self.tokens_validos = {"pat-valido"}
        self.falhas_429 = 0
        self.buscas: list[dict] = []
        self.requisicoes: list[httpx.Request] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._tratar)

    def _pagina(self, registros: list, depois: str | None, associacoes: str | None = None) -> dict:
        inicio = int(depois or 0)
        fim = inicio + self.tamanho
        itens = []
        for r in registros[inicio:fim]:
            item = dict(r)
            if not associacoes:
                item.pop("associations", None)
            itens.append(item)
        corpo = {"results": itens}
        if fim < len(registros):
            corpo["paging"] = {"next": {"after": str(fim), "link": f"https://api.hubapi.com/x?after={fim}"}}
        return corpo

    def _tratar(self, request: httpx.Request) -> httpx.Response:
        self.requisicoes.append(request)
        caminho = request.url.path
        if caminho == "/oauth/v1/token":
            dados = dict(x.split("=", 1) for x in request.content.decode().split("&"))
            if dados.get("refresh_token") != "refresh-ok":
                return httpx.Response(400, json={"status": "BAD_REFRESH_TOKEN"})
            self.tokens_validos.add("tok-renovado")
            return httpx.Response(200, json={"access_token": "tok-renovado", "refresh_token": "refresh-novo", "expires_in": 1800})
        if request.headers.get("Authorization", "").removeprefix("Bearer ") not in self.tokens_validos:
            return httpx.Response(401, json={"status": "error", "category": "EXPIRED_AUTHENTICATION"})
        if self.falhas_429:
            self.falhas_429 -= 1
            return httpx.Response(429, json={"status": "error", "errorType": "RATE_LIMIT"})
        if caminho == "/crm/v3/pipelines/deals":
            return httpx.Response(200, json=PIPELINES)
        if caminho == "/crm/v4/associations/deals/companies/batch/read":
            ids = [i["id"] for i in json.loads(request.content)["inputs"]]
            return httpx.Response(200, json={"status": "COMPLETE", "results": [
                {"from": {"id": i}, "to": [{"toObjectId": int(DEAL_EMPRESA[i]), "associationTypes": []}]} for i in ids if i in DEAL_EMPRESA]})
        objeto = caminho.split("/")[4]
        if caminho.endswith("/search"):
            corpo = json.loads(request.content)
            self.buscas.append(corpo)
            filtro = corpo["filterGroups"][0]["filters"][0]
            registros = [r for r in OBJETOS[objeto] if _ms(r["properties"][filtro["propertyName"]]) > int(filtro["value"])]
            return httpx.Response(200, json={"total": len(registros), **self._pagina(registros, corpo.get("after"))})
        params = request.url.params
        return httpx.Response(200, json=self._pagina(OBJETOS[objeto], params.get("after"), params.get("associations")))


@pytest.fixture()
def fake_hs(monkeypatch) -> FakeHubSpot:
    fake = FakeHubSpot()
    monkeypatch.setattr(http_base, "TRANSPORTE_PADRAO", fake.transport())
    return fake


def _adapter(fake: FakeHubSpot, credenciais=None, **config) -> HubSpotAdapter:
    return HubSpotAdapter(TENANT, credenciais or CREDENCIAIS, {"campo_cnpj": "cnpj", **config}, transport=fake.transport())


# --- Validação ---------------------------------------------------------------------------------


@pytest.mark.parametrize("credenciais,config", [
    ({}, {}), ({"refresh_token": "r", "client_id": "c"}, {}), ({**CREDENCIAIS, "base_url": "https://169.254.169.254"}, {}),
    (CREDENCIAIS, {"campo_cnpj": "cnpj,hs_secret"}), (CREDENCIAIS, {"moeda": "real"}),
])
def test_credenciais_e_configuracao_invalidas_sao_recusadas(credenciais, config):
    with pytest.raises(ValueError):
        validar(credenciais, config)


# --- Contrato e mapeamento ------------------------------------------------------------------------


def test_contrato_do_adapter_paginas_ate_o_fim_e_isolamento():
    fake = FakeHubSpot()
    dados = verificar_contrato(_adapter(fake), TENANT, "hubspot")
    assert len(dados["accounts"]) == 3 and any(r.url.params.get("after") == "2" for r in fake.requisicoes)
    assert len(dados["opportunities"]) == 3  # negócio sem empresa não é atribuído a ninguém
    assert {r.url.host for r in fake.requisicoes} == {"api.hubapi.com"}


def test_mapeamento_de_empresas_contatos_negocios_e_engajamentos():
    dados = coletar(_adapter(FakeHubSpot(), moeda="USD"), TENANT)
    orgs = {o.source.external_id: o for o in dados["organizations"]}
    assert (orgs["101"].legal_name, orgs["101"].domain, orgs["101"].tax_id, orgs["101"].size) == ("ACME Ltda", "acme.com.br", "11222333000181", "250")
    assert orgs["102"].domain is None and orgs["102"].tax_id is None
    ciclos = {a.source.external_id: a.lifecycle for a in dados["accounts"]}
    assert ciclos == {"101": AccountLifecycle.CUSTOMER, "102": AccountLifecycle.QUALIFIED, "103": AccountLifecycle.CUSTOMER}
    # Gama é cliente mas sem data de entrada: não vira Customer (data não é inventada)
    assert [(c.account_id, c.customer_since) for c in dados["customers"]] == [("hubspot:account:101", datetime(2026, 1, 5, tzinfo=UTC))]

    pessoas = {p.source.external_id: p for p in dados["people"]}
    assert pessoas["201"].full_name == "Ana Souza" and pessoas["201"].suppressed_at is not None
    assert pessoas["202"].full_name == "solto@x.com" and pessoas["202"].organization_id is None
    assert [c.account_id for c in dados["contacts"]] == ["hubspot:account:101"]

    assert {s.name: s.stage_type for s in dados["stages"]} == {
        "Appointment Scheduled": StageType.OPEN, "Closed Won": StageType.WON, "Closed Lost": StageType.LOST}
    ops = {o.name: o for o in dados["opportunities"]}
    assert ops["Licenças 2026"].status == OpportunityStatus.WON and ops["Licenças 2026"].amount.currency == "BRL"
    assert ops["Licenças 2026"].probability == 100 and ops["Licenças 2026"].closed_at == datetime(2026, 1, 5, tzinfo=UTC)
    assert ops["Expansão"].amount.amount == Decimal("1200.50") and ops["Expansão"].amount.currency == "USD"  # sem moeda no negócio
    assert ops["Expansão"].closed_at is None and ops["Piloto"].amount is None and ops["Piloto"].status == OpportunityStatus.LOST
    assert ops["Piloto"].account_id == "hubspot:account:102"

    atividades = {a.description: a for a in dados["activities"]}
    assert atividades["Ligação de follow-up"].kind == ActivityKind.CALL
    assert atividades["Ligação de follow-up"].opportunity_id == "hubspot:opportunity:301"
    assert atividades["Reunião trimestral"].kind == ActivityKind.MEETING
    assert atividades["Pediu  proposta"].kind == ActivityKind.NOTE  # HTML da nota removido
    assert atividades["Tarefa solta"].account_id is None
    assert {i.kind for i in dados["interactions"]} == {"contato"} and len(dados["interactions"]) == 3
    assert [o.name for o in dados["offers"]] == ["Plataforma"] and dados["cs_metrics"] == []


def test_interacoes_por_conta_sao_lidas_uma_vez():
    fake = FakeHubSpot()
    adapter = _adapter(fake)
    assert [i.description for i in iterar_todos(adapter.list_interactions, TENANT, account_id="hubspot:account:103")] == ["Reunião trimestral"]
    antes = len(fake.requisicoes)
    assert len(adapter.list_interactions(TENANT, account_id="hubspot:account:101").items) == 1
    assert len(fake.requisicoes) == antes


def test_updated_since_usa_a_search_api_com_epoch_ms():
    fake = FakeHubSpot()
    pagina = _adapter(fake).list_accounts(TENANT, updated_since=datetime(2026, 2, 1))
    filtro = fake.buscas[-1]["filterGroups"][0]["filters"][0]
    assert filtro == {"propertyName": "hs_lastmodifieddate", "operator": "GT", "value": str(_ms("2026-02-01T00:00:00Z"))}
    assert [a.source.external_id for a in pagina.items] == ["102"]
    _adapter(fake).list_people(TENANT, updated_since=datetime(2026, 2, 1))
    assert fake.buscas[-1]["filterGroups"][0]["filters"][0]["propertyName"] == "lastmodifieddate"


def test_cursor_forjado_e_recusado():
    with pytest.raises(ValueError):
        _adapter(FakeHubSpot()).list_accounts(TENANT, cursor="../../../oauth")


# --- Auth e resiliência --------------------------------------------------------------------------


def _conexao(db, credenciais=None) -> ConexaoIntegracao:
    conexao = ConexaoIntegracao(tenant_id=TENANT, sistema="hubspot", nome="HS", status="ativa",
                                configuracao={}, credenciais=json.dumps(credenciais or CREDENCIAIS))
    db.add(conexao)
    db.commit()
    return conexao


def test_429_e_retentado_e_segundo_sync_e_incremental(db_session, fake_hs):
    conexao = _conexao(db_session)
    fake_hs.falhas_429 = 2
    primeira = sync.sincronizar(db_session, conexao, "opportunities", dormir=lambda s: None)
    assert (primeira.status, primeira.itens_lidos, primeira.paginas) == ("sucesso", 3, 2)
    assert not fake_hs.buscas
    segunda = sync.sincronizar(db_session, conexao, "opportunities", dormir=lambda s: None)
    assert segunda.status == "sucesso" and segunda.incremental_desde is not None and fake_hs.buscas


def test_401_nao_e_retentado_e_token_renovado_e_persistido(db_session, fake_hs):
    expirada = _conexao(db_session, {"access_token": "pat-revogado"})
    execucao = sync.sincronizar(db_session, expirada, "accounts", dormir=lambda s: None)
    assert execucao.status == "falha" and len(fake_hs.requisicoes) == 1 and expirada.status == "erro"
    assert "pat-revogado" not in expirada.ultimo_erro

    oauth = _conexao(db_session, {"access_token": "tok-expirado", "refresh_token": "refresh-ok", "client_id": "c", "client_secret": "s"})
    assert sync.sincronizar(db_session, oauth, "accounts", dormir=lambda s: None).status == "sucesso"
    db_session.expire_all()
    salvas = json.loads(db_session.get(ConexaoIntegracao, oauth.id).credenciais)
    assert (salvas["access_token"], salvas["refresh_token"]) == ("tok-renovado", "refresh-novo")

    ruim = HubSpotAdapter(TENANT, {"access_token": "x", "refresh_token": "revogado", "client_id": "c", "client_secret": "s"},
                          transport=fake_hs.transport())
    with pytest.raises(ErroCredencial):
        ruim.list_accounts(TENANT)


# --- Hub e MAP ------------------------------------------------------------------------------------


def test_hubspot_e_beta_e_conecta_so_habilitado(client, fake_hs, monkeypatch):
    conector = next(c for c in client.get(f"{H}/conectores").json() if c["sistema"] == "hubspot")
    assert (conector["status"], conector["conectavel"]) == ("BETA", False)
    corpo = {"sistema": "hubspot", "nome": "HS", "credenciais": CREDENCIAIS}
    assert client.post(f"{H}/conexoes", json=corpo).status_code == 422
    monkeypatch.setattr(settings, "conectores_crm_habilitados", "salesforce,hubspot")
    resposta = client.post(f"{H}/conexoes", json=corpo)
    assert resposta.status_code == 201 and "pat-valido" not in resposta.text
    assert client.post(f"{H}/conexoes/{resposta.json()['id']}/sincronizar/people").json()["itens_lidos"] == 2


def test_map_sobre_a_conexao_hubspot_da_o_mesmo_resultado_que_o_payload(client, fake_hs, monkeypatch):
    monkeypatch.setattr(settings, "conectores_crm_habilitados", "hubspot")
    conexao = client.post(f"{H}/conexoes", json={"sistema": "hubspot", "nome": "HS", "credenciais": CREDENCIAIS}).json()
    dados = coletar(HubSpotAdapter(TENANT, CREDENCIAIS, transport=fake_hs.transport()), TENANT)
    payload = {chave: [i.model_dump(mode="json") for i in dados[chave]]
               for chave in ("organizations", "accounts", "customers", "opportunities", "stages", "interactions", "cs_metrics")}
    segredo = client.post("/api/v1/chaves-api", json={"nome": "hs", "escopos": ["map:read"]}).json()["segredo"]
    via_conexao = client.post("/api/v1/map/analyze", json={"periodo": "2026-01", "conexao_id": conexao["id"]}, headers={"X-API-Key": segredo}).json()
    via_payload = client.post("/api/v1/map/analyze", json={"periodo": "2026-01", "dados": payload}, headers={"X-API-Key": segredo}).json()
    assert via_conexao["fonte"] == "conexao:hubspot" and via_conexao["economia"] == via_payload["economia"]
    assert [(c["conta_id"], c["score"]) for c in via_conexao["contas"]] == [(c["conta_id"], c["score"]) for c in via_payload["contas"]]
