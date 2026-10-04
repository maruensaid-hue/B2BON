"""D-087 — formato da ESCRITA de cada conector contra um servidor falso no
formato documentado da API (mesma abordagem dos testes de leitura da Fase 13).

Para cada CRM: procura antes de criar (e não altera o que encontrou),
associações/vínculos corretos, campos PRÓPRIOS da B2B ON nos sinais e no
opt-out, ids validados antes de irem para a URL (anti path-injection),
literais SOQL escapados, token do RD Station só na query e mascarado, NPS
por campo configurado e OAuth do Pipedrive no domínio da empresa.
"""

import json
from datetime import UTC, date, datetime

import httpx
import pytest

from app.contexts.integrations.adapters.http_base import ErroConector
from app.contexts.integrations.adapters.hubspot import ASSOCIACOES, HubSpotAdapter
from app.contexts.integrations.adapters.pipedrive import PipedriveAdapter
from app.contexts.integrations.adapters.rd_station import RdStationCrmAdapter
from app.contexts.integrations.adapters.salesforce import SalesforceAdapter
from app.contexts.integrations.contract import (
    AtividadeSaida,
    CamposProprios,
    EmpresaSaida,
    NegocioSaida,
    OperacaoNaoSuportada,
    PessoaSaida,
    SinaisContaSaida,
    TarefaSaida,
    TipoAtividadeSaida,
    iterar_todos,
)
from app.core.config import settings

TENANT = "tenant-teste"
QUANDO = datetime(2026, 10, 10, 15, 0, tzinfo=UTC)


class Servidor:
    """Responde por (método, caminho) e grava cada requisição."""

    def __init__(self, rotas: dict):
        self.rotas = rotas
        self.pedidos: list[httpx.Request] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._tratar)

    def _tratar(self, request: httpx.Request) -> httpx.Response:
        self.pedidos.append(request)
        chave = (request.method, request.url.path)
        resposta = self.rotas.get(chave)
        if callable(resposta):
            resposta = resposta(request)
        if resposta is None:
            return httpx.Response(404, json={"message": f"rota falsa ausente: {chave}"})
        if isinstance(resposta, httpx.Response):
            return resposta
        return httpx.Response(200, json=resposta)

    def corpo(self, metodo: str, caminho: str) -> dict:
        pedido = next(p for p in self.pedidos if p.method == metodo and p.url.path == caminho)
        return json.loads(pedido.content)

    def metodos(self) -> list[tuple[str, str]]:
        return [(p.method, p.url.path) for p in self.pedidos]


# --- HubSpot -----------------------------------------------------------------------------
def _hubspot(rotas, **config) -> tuple[HubSpotAdapter, Servidor]:
    servidor = Servidor(rotas)
    return HubSpotAdapter(TENANT, {"access_token": "pat-valido"}, config, transport=servidor.transport()), servidor


def _busca_hubspot(achados: dict):
    def responder(request):
        filtro = json.loads(request.content)["filterGroups"][0]["filters"][0]
        id_ = achados.get((filtro["propertyName"], filtro["value"]))
        return {"results": [{"id": id_}] if id_ else []}
    return responder


def test_hubspot_empresa_existente_nao_e_alterada_e_nova_e_criada():
    adapter, servidor = _hubspot({
        ("POST", "/crm/v3/objects/companies/search"): _busca_hubspot({("cnpj", "11222333000181"): "555"}),
        ("POST", "/crm/v3/objects/companies"): {"id": "777"},
    }, campo_cnpj="cnpj")
    assert adapter.garantir_empresa(TENANT, EmpresaSaida(nome="ACME", cnpj="11222333000181", dominio="acme.com.br")) == "555"
    assert ("POST", "/crm/v3/objects/companies") not in servidor.metodos()
    assert not any(m in ("PATCH", "PUT") for m, _ in servidor.metodos())

    novo = adapter.garantir_empresa(TENANT, EmpresaSaida(nome="Nova", cnpj="99888777000166", dominio="nova.com", dono_externo_id="9001"))
    assert novo == "777"
    assert servidor.corpo("POST", "/crm/v3/objects/companies")["properties"] == {
        "name": "Nova", "domain": "nova.com", "hubspot_owner_id": "9001", "cnpj": "99888777000166"}


def test_hubspot_contato_associado_a_empresa_e_atividades_com_associacoes():
    adapter, servidor = _hubspot({
        ("POST", "/crm/v3/objects/contacts/search"): {"results": []},
        ("POST", "/crm/v3/objects/contacts"): {"id": "201"},
        ("POST", "/crm/v3/objects/meetings"): {"id": "301"},
        ("POST", "/crm/v3/objects/notes"): {"id": "302"},
        ("POST", "/crm/v3/objects/emails"): {"id": "303"},
        ("POST", "/crm/v3/objects/deals"): {"id": "401"},
        ("POST", "/crm/v3/objects/tasks"): {"id": "501"},
    })
    assert adapter.garantir_pessoa(TENANT, PessoaSaida(nome="Ana Maria Souza", email="Ana@acme.com.br", empresa_id="555")) == "201"
    contato = servidor.corpo("POST", "/crm/v3/objects/contacts")
    assert contato["properties"]["firstname"] == "Ana" and contato["properties"]["lastname"] == "Maria Souza"
    assert contato["associations"] == [{"to": {"id": "555"}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 279}]}]

    adapter.registrar_atividade(TENANT, AtividadeSaida(tipo=TipoAtividadeSaida.REUNIAO, assunto="Reunião", ocorrida_em=QUANDO, duracao_minutos=30,
                                                       empresa_id="555", pessoa_id="201", negocio_id="401"))
    reuniao = servidor.corpo("POST", "/crm/v3/objects/meetings")
    assert reuniao["properties"]["hs_meeting_end_time"] == str(int(QUANDO.timestamp() * 1000) + 30 * 60 * 1000)
    assert {a["types"][0]["associationTypeId"] for a in reuniao["associations"]} == {
        ASSOCIACOES[("meetings", "companies")], ASSOCIACOES[("meetings", "contacts")], ASSOCIACOES[("meetings", "deals")]}

    adapter.registrar_atividade(TENANT, AtividadeSaida(tipo=TipoAtividadeSaida.WHATSAPP, assunto="Olá", descricao="Texto", ocorrida_em=QUANDO, empresa_id="555"))
    assert servidor.corpo("POST", "/crm/v3/objects/notes")["properties"]["hs_note_body"].startswith("[WhatsApp] Olá")
    adapter.registrar_atividade(TENANT, AtividadeSaida(tipo=TipoAtividadeSaida.EMAIL, assunto="Assunto", ocorrida_em=QUANDO, pessoa_id="201"))
    assert servidor.corpo("POST", "/crm/v3/objects/emails")["properties"]["hs_email_direction"] == "EMAIL"

    adapter.criar_negocio(TENANT, NegocioSaida(nome="ACME — reunião", empresa_id="555", pessoa_id="201", estagio_id="appointmentscheduled"))
    negocio = servidor.corpo("POST", "/crm/v3/objects/deals")
    assert negocio["properties"] == {"dealname": "ACME — reunião", "pipeline": "default", "dealstage": "appointmentscheduled"}
    assert {a["types"][0]["associationTypeId"] for a in negocio["associations"]} == {341, 3}

    adapter.criar_tarefa(TENANT, TarefaSaida(assunto="Conta em risco", vencimento=date(2026, 10, 4), empresa_id="555"))
    assert servidor.corpo("POST", "/crm/v3/objects/tasks")["properties"]["hs_task_status"] == "NOT_STARTED"


def test_hubspot_sinais_e_optout_so_em_campos_proprios_e_ids_validados():
    adapter, servidor = _hubspot({
        ("PATCH", "/crm/v3/objects/companies/555"): {"id": "555"},
        ("PATCH", "/crm/v3/objects/contacts/201"): {"id": "201"},
    })
    campos = CamposProprios(score_risco="b2bon_score_risco", nivel_risco="b2bon_nivel_risco")
    adapter.gravar_sinais_conta(TENANT, SinaisContaSaida(empresa_id="555", score_risco=81.27, nivel_risco="critico"), campos)
    assert servidor.corpo("PATCH", "/crm/v3/objects/companies/555") == {"properties": {"b2bon_score_risco": "81.3", "b2bon_nivel_risco": "critico"}}
    adapter.marcar_optout(TENANT, "201", CamposProprios())
    assert servidor.corpo("PATCH", "/crm/v3/objects/contacts/201") == {"properties": {"b2bon_opt_out": "true"}}
    with pytest.raises(ValueError):
        adapter.marcar_optout(TENANT, "../../owners", CamposProprios())
    with pytest.raises(OperacaoNaoSuportada):
        adapter.gravar_sinais_conta(TENANT, SinaisContaSaida(empresa_id="555", score_risco=1, nivel_risco="saudavel"), CamposProprios())


def test_hubspot_preparar_campos_aceita_ja_existente():
    respostas = iter([httpx.Response(201, json={"name": "b2bon_score_risco"}), httpx.Response(409, json={"message": "already exists"}),
                      httpx.Response(201, json={"name": "b2bon_opt_out"})])
    adapter, servidor = _hubspot({
        ("POST", "/crm/v3/properties/companies"): lambda r: next(respostas),
        ("POST", "/crm/v3/properties/contacts"): lambda r: next(respostas),
    })
    campos = adapter.preparar_campos(TENANT)
    assert campos == CamposProprios(score_risco="b2bon_score_risco", nivel_risco="b2bon_nivel_risco", optout="b2bon_opt_out")
    assert len(servidor.pedidos) == 3


def test_hubspot_erro_de_validacao_na_escrita_traz_motivo_mascarado():
    adapter, _ = _hubspot({("POST", "/crm/v3/objects/deals"): httpx.Response(400, json={"message": "Property dealstage invalid access_token=abc"})})
    with pytest.raises(ErroConector) as erro:
        adapter.criar_negocio(TENANT, NegocioSaida(nome="N", empresa_id="1", estagio_id="x"))
    assert erro.value.status == 400 and "dealstage" in str(erro.value) and "abc" not in str(erro.value)


def test_hubspot_nps_por_propriedade_configurada():
    adapter, servidor = _hubspot({("GET", "/crm/v3/objects/companies"): {"results": [
        {"id": "1", "properties": {"nps_atual": "9"}, "updatedAt": "2026-09-01T00:00:00Z"},
        {"id": "2", "properties": {"nps_atual": "42"}, "updatedAt": "2026-09-01T00:00:00Z"},
        {"id": "3", "properties": {"nps_atual": None}, "updatedAt": "2026-09-01T00:00:00Z"},
    ]}}, campo_nps="nps_atual")
    metricas = iterar_todos(adapter.list_cs_metrics, TENANT)
    assert [(m.account_id, m.value, m.metric) for m in metricas] == [("hubspot:account:1", 9.0, "NPS")]
    assert "nps_atual" in servidor.pedidos[0].url.params["properties"]
    assert iterar_todos(adapter.list_cs_metrics, "outro-tenant") == []


def test_outro_tenant_nao_escreve_pela_conexao():
    adapter, servidor = _hubspot({})
    with pytest.raises(PermissionError):
        adapter.garantir_empresa("outro-tenant", EmpresaSaida(nome="X"))
    assert not servidor.pedidos


# --- Pipedrive ----------------------------------------------------------------------------
TOKEN_PD = "a" * 40


def _pipedrive(rotas, credenciais=None, **config) -> tuple[PipedriveAdapter, Servidor]:
    servidor = Servidor(rotas)
    return PipedriveAdapter(TENANT, credenciais or {"api_token": TOKEN_PD}, config, transport=servidor.transport()), servidor


def test_pipedrive_procura_por_cnpj_nome_e_email_antes_de_criar():
    adapter, servidor = _pipedrive({
        ("GET", "/v1/organizations/search"): lambda r: {"data": {"items": [{"item": {"id": 12}}] if r.url.params["fields"] == "name" else []}},
        ("GET", "/v1/persons/search"): {"data": {"items": []}},
        ("POST", "/v1/persons"): {"data": {"id": 34}},
    }, campo_cnpj="abc123")
    assert adapter.garantir_empresa(TENANT, EmpresaSaida(nome="ACME", cnpj="11222333000181")) == "12"
    buscas = [p.url.params["fields"] for p in servidor.pedidos if p.url.path == "/v1/organizations/search"]
    assert buscas == ["custom_fields", "name"]
    assert adapter.garantir_pessoa(TENANT, PessoaSaida(nome="Ana", email="ana@acme.com.br", telefone="+55", empresa_id="12", dono_externo_id="5")) == "34"
    assert servidor.corpo("POST", "/v1/persons") == {"name": "Ana", "email": [{"value": "ana@acme.com.br", "primary": True}],
                                                     "phone": [{"value": "+55", "primary": True}], "org_id": 12, "owner_id": 5}
    assert all(p.headers["x-api-token"] == TOKEN_PD and "api_token" not in str(p.url) for p in servidor.pedidos)


def test_pipedrive_negocio_atividades_nota_escapada_e_tarefa():
    adapter, servidor = _pipedrive({
        ("POST", "/v1/deals"): {"data": {"id": 90}},
        ("POST", "/v1/activities"): {"data": {"id": 91}},
        ("POST", "/v1/notes"): {"data": {"id": 92}},
    })
    adapter.criar_negocio(TENANT, NegocioSaida(nome="N", empresa_id="12", pessoa_id="34", estagio_id="7", previsao_fechamento=date(2026, 11, 9)))
    assert servidor.corpo("POST", "/v1/deals") == {"title": "N", "org_id": 12, "person_id": 34, "stage_id": 7, "expected_close_date": "2026-11-09"}
    adapter.registrar_atividade(TENANT, AtividadeSaida(tipo=TipoAtividadeSaida.LIGACAO, assunto="Ligação", ocorrida_em=QUANDO, negocio_id="90"))
    atividade = servidor.corpo("POST", "/v1/activities")
    assert atividade["type"] == "call" and atividade["done"] == 1 and atividade["due_date"] == "2026-10-10" and atividade["deal_id"] == 90
    adapter.registrar_atividade(TENANT, AtividadeSaida(tipo=TipoAtividadeSaida.NOTA, assunto="<script>x</script>", descricao="a\nb", ocorrida_em=QUANDO, empresa_id="12"))
    nota = servidor.corpo("POST", "/v1/notes")
    assert "<script>" not in nota["content"] and "&lt;script&gt;" in nota["content"] and "a<br>b" in nota["content"]
    with pytest.raises(ValueError):
        adapter.criar_negocio(TENANT, NegocioSaida(nome="N", empresa_id="12 OR 1=1", estagio_id="7"))


def test_pipedrive_sinais_optout_e_preparar_campos():
    adapter, servidor = _pipedrive({
        ("PUT", "/v1/organizations/12"): {"data": {"id": 12}},
        ("PUT", "/v1/persons/34"): {"data": {"id": 34}},
        ("GET", "/v1/organizationFields"): {"data": [{"name": "B2B ON — score de risco", "key": "hash_score"}]},
        ("POST", "/v1/organizationFields"): {"data": {"key": "hash_nivel"}},
        ("GET", "/v1/personFields"): {"data": []},
        ("POST", "/v1/personFields"): {"data": {"key": "hash_optout"}},
    })
    campos = adapter.preparar_campos(TENANT)
    assert campos == CamposProprios(score_risco="hash_score", nivel_risco="hash_nivel", optout="hash_optout")
    adapter.gravar_sinais_conta(TENANT, SinaisContaSaida(empresa_id="12", score_risco=50, nivel_risco="atencao"), campos)
    assert servidor.corpo("PUT", "/v1/organizations/12") == {"hash_score": 50, "hash_nivel": "atencao"}
    adapter.marcar_optout(TENANT, "34", campos)
    assert servidor.corpo("PUT", "/v1/persons/34") == {"hash_optout": "sim"}


def test_pipedrive_oauth_usa_dominio_da_empresa_e_renova(monkeypatch):
    monkeypatch.setattr(settings, "oauth_pipedrive_client_id", "cid")
    monkeypatch.setattr(settings, "oauth_pipedrive_client_secret", "csecret")
    chamadas = {"n": 0}

    def organizacoes(request):
        chamadas["n"] += 1
        if request.headers["Authorization"] == "Bearer velho":
            return httpx.Response(401, json={})
        return {"data": [{"id": 1, "name": "ACME"}], "additional_data": {"pagination": {"more_items_in_collection": False}}}

    renovado = {}
    servidor = Servidor({("GET", "/v1/organizations"): organizacoes,
                         ("POST", "/oauth/token"): lambda r: (renovado.update(auth=r.headers["Authorization"], corpo=r.content.decode())
                                                              or {"access_token": "novo", "refresh_token": "rt2", "api_domain": "https://acme.pipedrive.com"})})
    credenciais = {"oauth_app": "b2bon", "access_token": "velho", "refresh_token": "rt", "api_domain": "https://acme.pipedrive.com"}
    persistidas = []
    adapter = PipedriveAdapter(TENANT, credenciais, {}, transport=servidor.transport(), ao_renovar_token=persistidas.append)
    assert adapter.list_organizations(TENANT).items[0].legal_name == "ACME"
    hosts = {p.url.host for p in servidor.pedidos}
    assert hosts == {"acme.pipedrive.com", "oauth.pipedrive.com"}
    assert renovado["auth"].startswith("Basic ") and "grant_type=refresh_token" in renovado["corpo"]
    assert persistidas[0]["access_token"] == "novo"


def test_pipedrive_oauth_recusa_dominio_fora_do_pipedrive():
    with pytest.raises(ValueError):
        PipedriveAdapter(TENANT, {"oauth_app": "b2bon", "access_token": "x", "api_domain": "https://evil.example.com"}, {})


# --- Salesforce ---------------------------------------------------------------------------
SF = "https://acme.my.salesforce.com"
V = "/services/data/v60.0"


def _salesforce(rotas, **config) -> tuple[SalesforceAdapter, Servidor]:
    servidor = Servidor(rotas)
    return SalesforceAdapter(TENANT, {"instance_url": SF, "access_token": "tok"}, config, transport=servidor.transport()), servidor


def test_salesforce_soql_escapado_e_registro_encontrado_nao_alterado():
    consultas = []

    def query(request):
        consultas.append(request.url.params["q"])
        return {"records": [{"Id": "001000000000001AAA"}] if "Website" in request.url.params["q"] else [], "done": True}

    adapter, servidor = _salesforce({("GET", f"{V}/query"): query, ("POST", f"{V}/sobjects/Contact"): {"id": "003000000000001AAA", "success": True}},
                                    campo_cnpj="CNPJ__c")
    assert adapter.garantir_empresa(TENANT, EmpresaSaida(nome="ACME", cnpj="11222333000181", dominio="acme.com.br")) == "001000000000001AAA"
    assert consultas[0] == "SELECT Id FROM Account WHERE CNPJ__c IN ('11222333000181', '11.222.333/0001-81') LIMIT 1"
    assert consultas[1] == "SELECT Id FROM Account WHERE Website LIKE '%acme.com.br%' LIMIT 1"
    assert not any(m != "GET" for m, _ in servidor.metodos())

    adapter.garantir_pessoa(TENANT, PessoaSaida(nome="Madonna", email="o'brien@x.com", empresa_id="001000000000001AAA"))
    assert consultas[2] == "SELECT Id FROM Contact WHERE Email = 'o\\'brien@x.com' LIMIT 1"
    assert servidor.corpo("POST", f"{V}/sobjects/Contact") == {"LastName": "Madonna", "Email": "o'brien@x.com", "AccountId": "001000000000001AAA"}


def test_salesforce_dominio_suspeito_nao_entra_no_soql():
    adapter, servidor = _salesforce({("GET", f"{V}/query"): {"records": [], "done": True}, ("POST", f"{V}/sobjects/Account"): {"id": "001000000000002AAA"}})
    adapter.garantir_empresa(TENANT, EmpresaSaida(nome="X", dominio="x.com' OR Name LIKE '%"))
    assert not any(p.url.path == f"{V}/query" for p in servidor.pedidos)


def test_salesforce_oportunidade_exige_data_e_reuniao_vira_event():
    adapter, servidor = _salesforce({
        ("POST", f"{V}/sobjects/Opportunity"): {"id": "006000000000001AAA"},
        ("POST", f"{V}/sobjects/OpportunityContactRole"): httpx.Response(400, json=[{"message": "sem permissão"}]),
        ("POST", f"{V}/sobjects/Event"): {"id": "00U000000000001AAA"},
        ("POST", f"{V}/sobjects/Task"): {"id": "00T000000000001AAA"},
    })
    with pytest.raises(OperacaoNaoSuportada):
        adapter.criar_negocio(TENANT, NegocioSaida(nome="N", empresa_id="001000000000001AAA", estagio_id="Prospecting"))
    oportunidade = adapter.criar_negocio(TENANT, NegocioSaida(nome="N", empresa_id="001000000000001AAA", pessoa_id="003000000000001AAA",
                                                              estagio_id="Id. Decision Makers", previsao_fechamento=date(2026, 11, 9)))
    assert oportunidade == "006000000000001AAA"  # papel do contato falhou, oportunidade não duplica
    assert servidor.corpo("POST", f"{V}/sobjects/Opportunity")["StageName"] == "Id. Decision Makers"
    adapter.registrar_atividade(TENANT, AtividadeSaida(tipo=TipoAtividadeSaida.REUNIAO, assunto="R", ocorrida_em=QUANDO, duracao_minutos=30,
                                                       negocio_id=oportunidade, pessoa_id="003000000000001AAA"))
    evento = servidor.corpo("POST", f"{V}/sobjects/Event")
    assert evento["StartDateTime"] == "2026-10-10T15:00:00Z" and evento["EndDateTime"] == "2026-10-10T15:30:00Z"
    assert evento["WhatId"] == oportunidade and evento["WhoId"] == "003000000000001AAA"
    adapter.registrar_atividade(TENANT, AtividadeSaida(tipo=TipoAtividadeSaida.EMAIL, assunto="Olá", ocorrida_em=QUANDO, empresa_id="001000000000001AAA"))
    tarefa = servidor.corpo("POST", f"{V}/sobjects/Task")
    assert tarefa["Subject"] == "[E-mail] Olá" and tarefa["Status"] == "Completed" and tarefa["ActivityDate"] == "2026-10-10"


def test_salesforce_optout_padrao_e_sinais_em_campos_proprios():
    adapter, servidor = _salesforce({
        ("PATCH", f"{V}/sobjects/Contact/003000000000001AAA"): httpx.Response(204),
        ("PATCH", f"{V}/sobjects/Account/001000000000001AAA"): httpx.Response(204),
    })
    adapter.marcar_optout(TENANT, "003000000000001AAA", CamposProprios(optout="B2BON_Opt_Out__c"))
    assert servidor.corpo("PATCH", f"{V}/sobjects/Contact/003000000000001AAA") == {"HasOptedOutOfEmail": True, "B2BON_Opt_Out__c": True}
    adapter.gravar_sinais_conta(TENANT, SinaisContaSaida(empresa_id="001000000000001AAA", score_risco=70, nivel_risco="atencao"),
                                CamposProprios(score_risco="B2BON_Score_Risco__c", nivel_risco="B2BON_Nivel_Risco__c"))
    assert servidor.corpo("PATCH", f"{V}/sobjects/Account/001000000000001AAA") == {"B2BON_Score_Risco__c": 70, "B2BON_Nivel_Risco__c": "atencao"}
    with pytest.raises(ValueError):
        adapter.marcar_optout(TENANT, "003/../../sobjects/User", CamposProprios())
    with pytest.raises(OperacaoNaoSuportada):
        adapter.preparar_campos(TENANT)


def test_salesforce_nps_por_campo_configurado():
    adapter, servidor = _salesforce({("GET", f"{V}/query"): {"records": [
        {"Id": "001000000000001AAA", "NPS__c": 8, "LastModifiedDate": "2026-09-01T00:00:00.000+0000"},
        {"Id": "001000000000002AAA", "NPS__c": "n/a", "LastModifiedDate": "2026-09-01T00:00:00.000+0000"},
    ], "done": True}}, campo_nps="NPS__c")
    metricas = iterar_todos(adapter.list_cs_metrics, TENANT)
    assert [(m.account_id, m.value) for m in metricas] == [("salesforce:account:001000000000001AAA", 8.0)]
    assert "NPS__c != null" in servidor.pedidos[0].url.params["q"]


def test_campo_nps_invalido_e_recusado():
    with pytest.raises(ValueError):
        SalesforceAdapter(TENANT, {"instance_url": SF, "access_token": "t"}, {"campo_nps": "NPS__c FROM User --"})


# --- RD Station CRM -------------------------------------------------------------------------
TOKEN_RD = "token_rd_station_1234567890"


def _rd(rotas, **config) -> tuple[RdStationCrmAdapter, Servidor]:
    servidor = Servidor(rotas)
    return RdStationCrmAdapter(TENANT, {"token": TOKEN_RD}, config, transport=servidor.transport()), servidor


def test_rd_station_procura_cria_e_mantem_token_so_na_query():
    adapter, servidor = _rd({
        ("GET", "/api/v1/organizations"): {"organizations": [{"_id": "org1", "name": "ACME LTDA"}, {"_id": "org2", "name": "ACME Filial"}]},
        ("GET", "/api/v1/contacts"): {"contacts": []},
        ("POST", "/api/v1/contacts"): {"_id": "c1"},
        ("POST", "/api/v1/deals"): {"_id": "d1"},
        ("POST", "/api/v1/activities"): {"_id": "a1"},
    }, campo_cnpj="cf_cnpj")
    assert adapter.garantir_empresa(TENANT, EmpresaSaida(nome="acme ltda")) == "org1"
    assert adapter.garantir_pessoa(TENANT, PessoaSaida(nome="Ana", email="ana@acme.com.br", empresa_id="org1")) == "c1"
    assert servidor.corpo("POST", "/api/v1/contacts") == {"contact": {"name": "Ana", "emails": [{"email": "ana@acme.com.br"}], "organization_id": "org1"}}
    assert adapter.criar_negocio(TENANT, NegocioSaida(nome="N", empresa_id="org1", pessoa_id="c1", estagio_id="st1")) == "d1"
    assert servidor.corpo("POST", "/api/v1/deals") == {"deal": {"name": "N", "deal_stage_id": "st1"}, "organization": {"_id": "org1"}, "contacts": [{"_id": "c1"}]}
    adapter.registrar_atividade(TENANT, AtividadeSaida(tipo=TipoAtividadeSaida.EMAIL, assunto="Olá", ocorrida_em=QUANDO, negocio_id="d1"))
    assert servidor.corpo("POST", "/api/v1/activities")["activity"]["deal_id"] == "d1"
    for pedido in servidor.pedidos:
        assert pedido.url.params["token"] == TOKEN_RD
        assert TOKEN_RD not in pedido.content.decode()


def test_rd_station_sem_negociacao_nao_inventa_e_tarefa_nao_suportada():
    adapter, servidor = _rd({})
    with pytest.raises(OperacaoNaoSuportada):
        adapter.registrar_atividade(TENANT, AtividadeSaida(tipo=TipoAtividadeSaida.EMAIL, assunto="Olá", ocorrida_em=QUANDO, empresa_id="org1"))
    with pytest.raises(OperacaoNaoSuportada):
        adapter.criar_tarefa(TENANT, TarefaSaida(assunto="x", vencimento=date(2026, 10, 4), empresa_id="org1"))
    with pytest.raises(OperacaoNaoSuportada):
        adapter.marcar_optout(TENANT, "c1", CamposProprios())
    assert not servidor.pedidos


def test_rd_station_campos_personalizados_proprios():
    adapter, servidor = _rd({("PUT", "/api/v1/organizations/org1"): {"_id": "org1"}, ("PUT", "/api/v1/contacts/c1"): {"_id": "c1"}})
    adapter.gravar_sinais_conta(TENANT, SinaisContaSaida(empresa_id="org1", score_risco=12.34, nivel_risco="saudavel"),
                                CamposProprios(score_risco="cf_score", nivel_risco="cf_nivel"))
    assert servidor.corpo("PUT", "/api/v1/organizations/org1") == {"organization": {"organization_custom_fields": [
        {"custom_field_id": "cf_score", "value": "12.3"}, {"custom_field_id": "cf_nivel", "value": "saudavel"}]}}
    adapter.marcar_optout(TENANT, "c1", CamposProprios(optout="cf_optout"))
    assert servidor.corpo("PUT", "/api/v1/contacts/c1") == {"contact": {"contact_custom_fields": [{"custom_field_id": "cf_optout", "value": "sim"}]}}
    with pytest.raises(ValueError):
        adapter.gravar_sinais_conta(TENANT, SinaisContaSaida(empresa_id="org1/../x", score_risco=1, nivel_risco="a"), CamposProprios(score_risco="cf"))


def test_rd_station_nps_por_campo_personalizado():
    adapter, _ = _rd({("GET", "/api/v1/organizations"): {"organizations": [
        {"id": "org1", "custom_fields": [{"custom_field_id": "cf_nps", "value": "7,5"}], "updated_at": "2026-09-01T00:00:00Z"},
        {"id": "org2", "custom_fields": [], "updated_at": "2026-09-01T00:00:00Z"},
    ], "has_more": False}}, campo_nps="cf_nps")
    assert [(m.account_id, m.value) for m in iterar_todos(adapter.list_cs_metrics, TENANT)] == [("rd_station:account:org1", 7.5)]
