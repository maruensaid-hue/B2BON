"""Conector Salesforce (Fase 13, conector 1/4). GATE: contrato do adapter,
auth, retry, sync incremental, isolamento e paridade do MAP.

O servidor falso responde no formato documentado da REST API
(`/services/data/vXX.X/query`, `done`/`nextRecordsUrl`, erro
`INVALID_SESSION_ID` com 401) e interpreta o pedaço de SOQL que o
adapter usa (FROM, WHERE simples, LastModifiedDate >).
"""

import json
import re
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import text

from app.contexts.integrations import registry, sync
from app.contexts.integrations.adapters import http_base
from app.contexts.integrations.adapters.salesforce import SalesforceAdapter, validar
from app.contexts.integrations.contract import ErroCredencial, iterar_todos
from app.contexts.shared.canonical.commercial import AccountLifecycle, ActivityKind, OpportunityStatus, StageType
from app.core.config import settings
from app.models.conexao_integracao import ConexaoIntegracao
from tests.conectores_crm import coletar, verificar_contrato

TENANT = "tenant-teste"
INSTANCIA = "https://acme.my.salesforce.com"
CREDENCIAIS = {"instance_url": INSTANCIA, "access_token": "tok-valido"}
H = "/api/v1/hub-integracoes"


def _r(tipo: str, id_: str, **campos) -> dict:
    return {"attributes": {"type": tipo, "url": f"/services/data/v60.0/sobjects/{tipo}/{id_}"}, "Id": id_,
            "LastModifiedDate": "2026-01-10T12:00:00.000+0000", "CreatedDate": "2025-06-01T09:00:00.000+0000", **campos}


REGISTROS = {
    "Account": [
        _r("Account", "001000000000001AAA", Name="ACME Ltda", Website="https://www.acme.com.br", Industry="Manufacturing",
           NumberOfEmployees=250, BillingState="SP", Type="Customer - Direct", OwnerId="005A", CNPJ__c="11.222.333/0001-81"),
        _r("Account", "001000000000002AAA", Name="Beta SA", Website=None, Type="Prospect", OwnerId="005A",
           LastModifiedDate="2026-03-01T00:00:00.000+0000"),
        _r("Account", "001000000000003AAA", Name="Gama ME", Website="gama.com", Type="Customer - Channel", OwnerId="005B"),
    ],
    "Contact": [
        _r("Contact", "003000000000001AAA", AccountId="001000000000001AAA", Name="Ana Souza", Title="CFO",
           Email="ana@acme.com.br", Phone=None, HasOptedOutOfEmail=True),
        _r("Contact", "003000000000002AAA", AccountId=None, Name="Solto", Title=None, Email=None, Phone=None, HasOptedOutOfEmail=False),
    ],
    "OpportunityStage": [
        {"attributes": {"type": "OpportunityStage"}, "Id": "01J1", "ApiName": "Prospecting", "MasterLabel": "Prospecting", "SortOrder": 1, "IsClosed": False, "IsWon": False},
        {"attributes": {"type": "OpportunityStage"}, "Id": "01J2", "ApiName": "Closed Won", "MasterLabel": "Closed Won", "SortOrder": 2, "IsClosed": True, "IsWon": True},
        {"attributes": {"type": "OpportunityStage"}, "Id": "01J3", "ApiName": "Closed Lost", "MasterLabel": "Closed Lost", "SortOrder": 3, "IsClosed": True, "IsWon": False},
    ],
    "Opportunity": [
        _r("Opportunity", "006000000000001AAA", AccountId="001000000000001AAA", Name="Licenças 2026", Amount=5000.0, Probability=100.0,
           StageName="Closed Won", IsClosed=True, IsWon=True, CloseDate="2026-01-05", OwnerId="005A"),
        _r("Opportunity", "006000000000002AAA", AccountId="001000000000001AAA", Name="Expansão", Amount=1200.5, Probability=20.0,
           StageName="Prospecting", IsClosed=False, IsWon=False, CloseDate="2026-12-01", OwnerId="005A"),
        _r("Opportunity", "006000000000003AAA", AccountId="001000000000002AAA", Name="Piloto", Amount=None, Probability=0.0,
           StageName="Closed Lost", IsClosed=True, IsWon=False, CloseDate="2026-02-01", OwnerId="005A"),
        _r("Opportunity", "006000000000004AAA", AccountId=None, Name="Sem conta", Amount=10.0, Probability=10.0,
           StageName="Prospecting", IsClosed=False, IsWon=False, CloseDate="2026-12-01", OwnerId="005A"),
        _r("Opportunity", "006000000000005AAA", AccountId="001000000000003AAA", Name="Canal", Amount=800.0, Probability=100.0,
           StageName="Closed Won", IsClosed=True, IsWon=True, CloseDate="2025-11-20", OwnerId="005B"),
    ],
    "Task": [
        _r("Task", "00T000000000001AAA", AccountId="001000000000001AAA", WhatId="006000000000001AAA", Subject="Ligação de follow-up",
           TaskSubtype="Call", Type="Call", OwnerId="005A"),
        _r("Task", "00T000000000002AAA", AccountId="001000000000002AAA", WhatId="001000000000002AAA", Subject="Enviar material",
           TaskSubtype="Task", Type=None, OwnerId="005A"),
    ],
    "Event": [
        _r("Event", "00U000000000001AAA", AccountId="001000000000003AAA", WhatId=None, Subject="Reunião trimestral", Type="Meeting", OwnerId="005B"),
    ],
    "Product2": [
        {"attributes": {"type": "Product2"}, "Id": "01t000000000001AAA", "Name": "Plataforma", "Family": "Software", "Description": None, "IsActive": True},
    ],
}


class FakeSalesforce:
    """REST API do Salesforce em memória, paginando de 2 em 2."""

    def __init__(self, tamanho_pagina: int = 2) -> None:
        self.tamanho = tamanho_pagina
        self.tokens_validos = {"tok-valido"}
        self.falhas_429 = 0
        self.consultas: list[str] = []
        self.requisicoes: list[httpx.Request] = []
        self._cursores: dict[str, tuple[list, int]] = {}

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._tratar)

    def _filtrar(self, soql: str) -> list[dict]:
        objeto = re.search(r"FROM (\w+)", soql).group(1)
        registros = list(REGISTROS[objeto])
        if m := re.search(r"LastModifiedDate > (\S+)", soql):
            limite = datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
            registros = [r for r in registros if datetime.fromisoformat(r["LastModifiedDate"].replace("+0000", "+00:00")) > limite]
        if "IsWon = true" in soql:
            registros = [r for r in registros if r["IsWon"]]
        if "AccountId != null" in soql:
            registros = [r for r in registros if r.get("AccountId")]
        if m := re.search(r"AccountId = '(\w+)'", soql):
            registros = [r for r in registros if r.get("AccountId") == m.group(1)]
        if "ORDER BY CloseDate" in soql:
            registros.sort(key=lambda r: r["CloseDate"])
        return registros

    def _pagina(self, registros: list, inicio: int) -> dict:
        fim = inicio + self.tamanho
        corpo = {"totalSize": len(registros), "done": fim >= len(registros), "records": registros[inicio:fim]}
        if fim < len(registros):
            chave = f"01gCURSOR{len(self._cursores)}-{fim}"
            self._cursores[chave] = (registros, fim)
            corpo["nextRecordsUrl"] = f"/services/data/v60.0/query/{chave}"
        return corpo

    def _tratar(self, request: httpx.Request) -> httpx.Response:
        self.requisicoes.append(request)
        if request.url.path == "/services/oauth2/token":
            dados = dict(x.split("=", 1) for x in request.content.decode().split("&"))
            if dados.get("refresh_token") != "refresh-ok":
                return httpx.Response(400, json={"error": "invalid_grant"})
            self.tokens_validos.add("tok-renovado")
            return httpx.Response(200, json={"access_token": "tok-renovado", "instance_url": INSTANCIA, "token_type": "Bearer"})
        if request.headers.get("Authorization", "").removeprefix("Bearer ") not in self.tokens_validos:
            return httpx.Response(401, json=[{"message": "Session expired or invalid", "errorCode": "INVALID_SESSION_ID"}])
        if self.falhas_429:
            self.falhas_429 -= 1
            return httpx.Response(429, json=[{"errorCode": "REQUEST_LIMIT_EXCEEDED"}])
        if request.url.path == "/services/data/v60.0/query":
            soql = request.url.params["q"]
            self.consultas.append(soql)
            return httpx.Response(200, json=self._pagina(self._filtrar(soql), 0))
        chave = request.url.path.rsplit("/", 1)[-1]
        registros, inicio = self._cursores[chave]
        return httpx.Response(200, json=self._pagina(registros, inicio))


@pytest.fixture()
def fake_sf(monkeypatch) -> FakeSalesforce:
    fake = FakeSalesforce()
    monkeypatch.setattr(http_base, "TRANSPORTE_PADRAO", fake.transport())
    return fake


@pytest.fixture()
def sf_habilitado(monkeypatch, fake_sf):
    monkeypatch.setattr(settings, "conectores_crm_habilitados", "salesforce")
    return fake_sf


def _adapter(fake: FakeSalesforce, credenciais=None, **config) -> SalesforceAdapter:
    return SalesforceAdapter(TENANT, credenciais or CREDENCIAIS, {"campo_cnpj": "CNPJ__c", **config}, transport=fake.transport())


# --- Validação de credenciais (anti-SSRF) -------------------------------------------------


@pytest.mark.parametrize("instancia", [
    "http://acme.my.salesforce.com", "https://169.254.169.254", "https://evil.com", "https://acme.salesforce.com.evil.com",
    "https://user@acme.my.salesforce.com", "https://acme.my.salesforce.com:8443", "salesforce.com",
])
def test_instance_url_fora_do_salesforce_e_recusada(instancia):
    with pytest.raises(ValueError):
        validar({"instance_url": instancia, "access_token": "x"}, {})


@pytest.mark.parametrize("config", [{"campo_cnpj": "Id FROM User --"}, {"campo_cnpj": "a,b"}, {"moeda": "reais"}])
def test_configuracao_nao_injeta_soql(config):
    with pytest.raises(ValueError):
        validar(CREDENCIAIS, config)


def test_login_url_e_refresh_validados():
    with pytest.raises(ValueError):
        validar({**CREDENCIAIS, "login_url": "https://evil.com"}, {})
    with pytest.raises(ValueError):
        validar({"instance_url": INSTANCIA, "refresh_token": "r"}, {})


# --- Contrato e mapeamento -------------------------------------------------------------------


def test_contrato_do_adapter_paginas_ate_o_fim_e_isolamento():
    fake = FakeSalesforce()
    dados = verificar_contrato(_adapter(fake), TENANT, "salesforce")
    assert len(dados["accounts"]) == 3 and any("/query/01gCURSOR" in str(r.url) for r in fake.requisicoes)
    assert len(dados["opportunities"]) == 4  # a oportunidade sem conta não é atribuída a ninguém
    assert not any(r.url.host != "acme.my.salesforce.com" for r in fake.requisicoes)


def test_mapeamento_de_contas_pessoas_e_oportunidades():
    dados = coletar(_adapter(FakeSalesforce(), moeda="USD"), TENANT)
    orgs = {o.source.external_id: o for o in dados["organizations"]}
    acme = orgs["001000000000001AAA"]
    assert (acme.legal_name, acme.domain, acme.tax_id, acme.size, acme.region) == ("ACME Ltda", "acme.com.br", "11222333000181", "250", "SP")
    assert orgs["001000000000003AAA"].domain == "gama.com" and orgs["001000000000002AAA"].tax_id is None
    ciclos = {a.source.external_id: a.lifecycle for a in dados["accounts"]}
    assert ciclos == {"001000000000001AAA": AccountLifecycle.CUSTOMER, "001000000000002AAA": AccountLifecycle.PROSPECT,
                      "001000000000003AAA": AccountLifecycle.CUSTOMER}

    ana = next(p for p in dados["people"] if p.full_name == "Ana Souza")
    assert ana.suppressed_at is not None and ana.organization_id == "salesforce:organization:001000000000001AAA"
    assert [c.person_id for c in dados["contacts"]] == ["salesforce:person:003000000000001AAA"]

    tipos = {s.name: s.stage_type for s in dados["stages"]}
    assert tipos == {"Prospecting": StageType.OPEN, "Closed Won": StageType.WON, "Closed Lost": StageType.LOST}
    ops = {o.name: o for o in dados["opportunities"]}
    assert ops["Licenças 2026"].status == OpportunityStatus.WON and ops["Licenças 2026"].closed_at == datetime(2026, 1, 5, tzinfo=UTC)
    assert ops["Expansão"].amount.amount == Decimal("1200.5") and ops["Expansão"].amount.currency == "USD"
    assert ops["Expansão"].closed_at is None and ops["Piloto"].amount is None and ops["Piloto"].status == OpportunityStatus.LOST

    clientes = {c.account_id: c.customer_since for c in dados["customers"]}
    assert clientes == {"salesforce:account:001000000000001AAA": datetime(2026, 1, 5, tzinfo=UTC),
                        "salesforce:account:001000000000003AAA": datetime(2025, 11, 20, tzinfo=UTC)}
    assert all(c.churned_at is None for c in dados["customers"])  # desconhecido, não inventado

    atividades = {a.description: a for a in dados["activities"]}
    assert atividades["Ligação de follow-up"].kind == ActivityKind.CALL
    assert atividades["Ligação de follow-up"].opportunity_id == "salesforce:opportunity:006000000000001AAA"
    assert atividades["Enviar material"].kind == ActivityKind.TASK and atividades["Enviar material"].opportunity_id is None
    assert atividades["Reunião trimestral"].kind == ActivityKind.MEETING
    assert {i.kind for i in dados["interactions"]} == {"contato"} and dados["cs_metrics"] == []
    assert [o.name for o in dados["offers"]] == ["Plataforma"]


def test_interacoes_filtradas_por_conta_e_id_malicioso_nao_vira_soql():
    fake = FakeSalesforce()
    adapter = _adapter(fake)
    itens = iterar_todos(adapter.list_interactions, TENANT, account_id="salesforce:account:001000000000003AAA")
    assert [i.description for i in itens] == ["Reunião trimestral"]
    antes = len(fake.consultas)
    assert adapter.list_interactions(TENANT, account_id="salesforce:account:x' OR Name != '").items == []
    assert len(fake.consultas) == antes


def test_updated_since_vira_filtro_de_lastmodifieddate():
    fake = FakeSalesforce()
    pagina = _adapter(fake).list_accounts(TENANT, updated_since=datetime(2026, 2, 1))
    assert "WHERE LastModifiedDate > 2026-02-01T00:00:00Z" in fake.consultas[-1]
    assert [a.source.external_id for a in pagina.items] == ["001000000000002AAA"]


# --- Auth e resiliência ---------------------------------------------------------------------------


def _conexao(db, credenciais=None) -> ConexaoIntegracao:
    conexao = ConexaoIntegracao(tenant_id=TENANT, sistema="salesforce", nome="SF", status="ativa",
                                configuracao={}, credenciais=json.dumps(credenciais or CREDENCIAIS))
    db.add(conexao)
    db.commit()
    return conexao


def test_429_e_retentado_e_sync_incremental_usa_a_ultima_execucao(db_session, fake_sf):
    conexao = _conexao(db_session)
    fake_sf.falhas_429 = 2
    recebidos = []
    primeira = sync.sincronizar(db_session, conexao, "accounts", destino=recebidos.extend, dormir=lambda s: None)
    assert (primeira.status, primeira.itens_lidos, primeira.paginas, primeira.tentativas) == ("sucesso", 3, 2, 4)
    assert primeira.incremental_desde is None and "WHERE" not in fake_sf.consultas[0]

    segunda = sync.sincronizar(db_session, conexao, "accounts", dormir=lambda s: None)
    assert segunda.status == "sucesso" and segunda.incremental_desde is not None
    assert "WHERE LastModifiedDate > " in fake_sf.consultas[-1]


def test_401_nao_e_retentado_e_marca_a_conexao_para_reconectar(db_session, fake_sf):
    conexao = _conexao(db_session, {"instance_url": INSTANCIA, "access_token": "tok-expirado"})
    execucao = sync.sincronizar(db_session, conexao, "accounts", dormir=lambda s: None)
    assert execucao.status == "falha" and execucao.tentativas == 0 and len(fake_sf.requisicoes) == 1
    assert conexao.status == "erro" and "Reconecte" in conexao.ultimo_erro and "tok-expirado" not in conexao.ultimo_erro


def test_token_expirado_e_renovado_uma_vez_e_persistido_criptografado(db_session, fake_sf):
    credenciais = {"instance_url": INSTANCIA, "access_token": "tok-expirado", "refresh_token": "refresh-ok", "client_id": "cid"}
    conexao = _conexao(db_session, credenciais)
    execucao = sync.sincronizar(db_session, conexao, "accounts", dormir=lambda s: None)
    assert execucao.status == "sucesso" and execucao.itens_lidos == 3
    db_session.expire_all()
    assert json.loads(db_session.get(ConexaoIntegracao, conexao.id).credenciais)["access_token"] == "tok-renovado"
    bruto = db_session.execute(text("SELECT credenciais FROM conexao_integracao WHERE id = :i"), {"i": conexao.id}).scalar()
    assert "tok-renovado" not in bruto and "refresh-ok" not in bruto

    ruim = SalesforceAdapter(TENANT, {**credenciais, "refresh_token": "revogado"}, transport=fake_sf.transport())
    with pytest.raises(ErroCredencial):
        ruim.list_accounts(TENANT)


# --- Hub (API) --------------------------------------------------------------------------------------


def test_salesforce_e_beta_e_so_conecta_quando_o_operador_habilita(client, fake_sf):
    conectores = {c["sistema"]: c for c in client.get(f"{H}/conectores").json()}
    assert (conectores["salesforce"]["status"], conectores["salesforce"]["conectavel"]) == ("BETA", False)
    corpo = {"sistema": "salesforce", "nome": "SF", "credenciais": CREDENCIAIS}
    assert client.post(f"{H}/conexoes", json=corpo).status_code == 422


def test_conexao_guarda_credencial_sem_devolver_e_sincroniza(client, db_session, sf_habilitado, criar_usuario_autenticado):
    assert client.post(f"{H}/conexoes", json={"sistema": "salesforce", "nome": "SF",
                                              "credenciais": {**CREDENCIAIS, "instance_url": "https://10.0.0.1"}}).status_code == 422
    resposta = client.post(f"{H}/conexoes", json={"sistema": "salesforce", "nome": "SF", "credenciais": CREDENCIAIS,
                                                   "configuracao": {"campo_cnpj": "CNPJ__c"}})
    assert resposta.status_code == 201, resposta.text
    conexao = resposta.json()
    assert "tok-valido" not in resposta.text and "tok-valido" not in client.get(f"{H}/conexoes").text

    execucao = client.post(f"{H}/conexoes/{conexao['id']}/sincronizar/opportunities").json()
    assert (execucao["status"], execucao["itens_lidos"]) == ("sucesso", 4)

    outro = criar_usuario_autenticado("tenant-b-sf", papel="admin", email="admin@b-sf.com")
    assert client.post(f"{H}/conexoes/{conexao['id']}/sincronizar/accounts", headers=outro).status_code == 404
    assert client.put(f"{H}/conexoes/{conexao['id']}/credenciais", json={"credenciais": CREDENCIAIS}, headers=outro).status_code == 404


def test_reconectar_troca_a_credencial_e_reativa(client, db_session, sf_habilitado):
    conexao = client.post(f"{H}/conexoes", json={"sistema": "salesforce", "nome": "SF",
                                                 "credenciais": {"instance_url": INSTANCIA, "access_token": "tok-expirado"}}).json()
    falha = client.post(f"{H}/conexoes/{conexao['id']}/sincronizar/accounts").json()
    assert falha["status"] == "falha"
    assert client.get(f"{H}/conexoes").json()[0]["status"] == "erro"
    assert client.put(f"{H}/conexoes/{conexao['id']}/credenciais", json={"credenciais": CREDENCIAIS}).status_code == 200
    assert client.post(f"{H}/conexoes/{conexao['id']}/sincronizar/accounts").json()["status"] == "sucesso"


def test_desabilitar_o_conector_bloqueia_sync_de_conexao_existente(client, sf_habilitado, monkeypatch):
    conexao = client.post(f"{H}/conexoes", json={"sistema": "salesforce", "nome": "SF", "credenciais": CREDENCIAIS}).json()
    monkeypatch.setattr(settings, "conectores_crm_habilitados", "")
    assert client.post(f"{H}/conexoes/{conexao['id']}/sincronizar/accounts").status_code == 422
    assert not registry.conectavel("salesforce")


def test_map_sobre_a_conexao_da_o_mesmo_resultado_que_o_payload_canonico(client, sf_habilitado):
    conexao = client.post(f"{H}/conexoes", json={"sistema": "salesforce", "nome": "SF", "credenciais": CREDENCIAIS}).json()
    dados = coletar(_adapter(sf_habilitado), TENANT)
    payload = {chave: [i.model_dump(mode="json") for i in dados[chave]]
               for chave in ("organizations", "accounts", "customers", "opportunities", "stages", "interactions", "cs_metrics")}
    segredo = client.post("/api/v1/chaves-api", json={"nome": "sf", "escopos": ["map:read"]}).json()["segredo"]
    periodo = "2026-01"
    via_conexao = client.post("/api/v1/map/analyze", json={"periodo": periodo, "conexao_id": conexao["id"]}, headers={"X-API-Key": segredo})
    assert via_conexao.status_code == 200, via_conexao.text
    via_payload = client.post("/api/v1/map/analyze", json={"periodo": periodo, "dados": payload}, headers={"X-API-Key": segredo}).json()
    via_conexao = via_conexao.json()
    assert via_conexao["fonte"] == "conexao:salesforce"
    assert via_conexao["economia"] == via_payload["economia"]
    assert [(c["conta_id"], c["score"]) for c in via_conexao["contas"]] == [(c["conta_id"], c["score"]) for c in via_payload["contas"]]
    assert client.post("/api/v1/map/analyze", json={"conexao_id": conexao["id"], "dados": payload}, headers={"X-API-Key": segredo}).status_code == 422
