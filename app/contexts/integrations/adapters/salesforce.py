"""Conector Salesforce ↔ modelo canônico (Fase 13, conector 1 de 4; escrita D-087).

Leitura via REST API (SOQL em `/services/data/vXX.X/query`,
paginação por `nextRecordsUrl`). Mapeamento em
`docs/b2bon/14_INTEGRATION_HUB.md` §Salesforce. Status BETA: validado
contra respostas no formato documentado da API (testes de contrato),
ainda não contra uma org real — por isso só conecta quando o operador
habilita (`CONECTORES_CRM_HABILITADOS`).

Credenciais (criptografadas em `ConexaoIntegracao.credenciais`):
`instance_url` + `access_token`, e opcionalmente `refresh_token` +
`client_id` (+ `client_secret`) para renovar o token expirado uma vez
por execução — ou `oauth_app: "b2bon"` (Connected App da B2B ON; client
id/secret vêm do servidor). Configuração: `moeda` (default BRL — Salesforce sem
multi-moeda não devolve moeda) e `campo_cnpj` (campo customizado da
Account com o CNPJ, ex.: `CNPJ__c`; sem ele, `tax_id` fica vazio).

Escrita (D-087) pelo sObject REST: Account procurada pelo CNPJ/Website e
Contact pelo e-mail (SOQL com literais escapados) — encontrados, não são
alterados; Opportunity (StageName + CloseDate obrigatórios), Task (atividade
concluída / tarefa aberta) e Event (reunião) criados. Opt-out: o padrão
`HasOptedOutOfEmail` (só restringe) + campo próprio, se configurado. Sinais do
MAP em campos customizados PRÓPRIOS que o admin cria (ex.:
`B2BON_Score_Risco__c`) — a API REST não cria campos.
"""

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from urllib.parse import urlsplit

import httpx

from app.contexts.integrations.adapters import interacoes
from app.contexts.integrations.adapters.http_base import AcessoBearer, host_permitido, persistidor
from app.contexts.integrations.adapters.http_base import ErroConector
from app.contexts.integrations.contract import (
    ESCRITAS,
    AdapterCapabilities,
    AtividadeSaida,
    CamposProprios,
    CrmAdapter,
    EmpresaSaida,
    ErroCredencial,
    NegocioSaida,
    OperacaoNaoSuportada,
    Page,
    PessoaSaida,
    SinaisContaSaida,
    TarefaSaida,
    TipoAtividadeSaida,
)
from app.core.config import settings
from app.contexts.shared.canonical.base import SourceRef, canonical_id
from app.contexts.shared.canonical.commercial import (
    Account,
    AccountLifecycle,
    Activity,
    ActivityKind,
    Contact,
    CSMetric,
    Customer,
    Interaction,
    Money,
    Offer,
    Opportunity,
    OpportunityStatus,
    Organization,
    Person,
    Pipeline,
    PipelineStage,
    StageType,
)

SYSTEM = "salesforce"
VERSAO_API = "v60.0"
HOSTS_API = (".salesforce.com", ".force.com")
HOSTS_LOGIN = ("login.salesforce.com", "test.salesforce.com", ".my.salesforce.com")
_CAMPO = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,79}$")
_MOEDA = re.compile(r"^[A-Z]{3}$")
PIPELINE_ID = canonical_id(SYSTEM, "pipeline", "default")

_LEGIVEIS = frozenset({
    "organizations", "accounts", "customers", "people", "contacts", "pipelines", "stages",
    "opportunities", "activities", "interactions", "offers",
})


def validar(credenciais: dict, configuracao: dict) -> None:
    """Levanta ValueError com mensagem para o usuário (nunca ecoa segredo)."""
    instancia = credenciais.get("instance_url")
    if not isinstance(instancia, str) or not host_permitido(instancia, HOSTS_API):
        raise ValueError("instance_url deve ser https://<sua-org>.my.salesforce.com")
    if not credenciais.get("access_token") and not credenciais.get("refresh_token"):
        raise ValueError("Informe access_token ou refresh_token.")
    app_b2bon = credenciais.get("oauth_app") == "b2bon"
    if "oauth_app" in credenciais and not app_b2bon:
        raise ValueError("oauth_app inválido.")
    if credenciais.get("refresh_token") and not credenciais.get("client_id") and not app_b2bon:
        raise ValueError("refresh_token exige client_id do Connected App.")
    login = credenciais.get("login_url", "https://login.salesforce.com")
    if not isinstance(login, str) or not host_permitido(login, HOSTS_LOGIN):
        raise ValueError("login_url deve ser https://login.salesforce.com ou https://test.salesforce.com")
    campo = configuracao.get("campo_cnpj")
    if campo is not None and not (isinstance(campo, str) and _CAMPO.match(campo)):
        raise ValueError("campo_cnpj deve ser o nome de API de um campo (ex.: CNPJ__c).")
    nps = configuracao.get("campo_nps")
    if nps is not None and not (isinstance(nps, str) and _CAMPO.match(nps)):
        raise ValueError("campo_nps deve ser o nome/id do campo com a nota NPS (0–10) da empresa.")
    moeda = configuracao.get("moeda", "BRL")
    if not (isinstance(moeda, str) and _MOEDA.match(moeda)):
        raise ValueError("moeda deve ser um código ISO 4217 (ex.: BRL).")


def cid(entidade: str, id_: str) -> str:
    return canonical_id(SYSTEM, entidade, id_)


def _src(entidade: str, id_: str, agora: datetime) -> SourceRef:
    return SourceRef(system=SYSTEM, external_id=id_, entity=entidade, fetched_at=agora)


def _data(valor: str | None) -> datetime | None:
    if not valor:
        return None
    if len(valor) == 10:  # campo Date (ex.: CloseDate)
        return datetime.fromisoformat(valor).replace(tzinfo=UTC)
    return datetime.fromisoformat(valor.replace("Z", "+00:00"))


def _literal_data(momento: datetime) -> str:
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=UTC)
    return momento.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dominio(site: str | None) -> str | None:
    if not site:
        return None
    host = urlsplit(site if "://" in site else f"https://{site}").hostname
    return host.removeprefix("www.") if host else None


def _lifecycle(tipo: str | None) -> AccountLifecycle:
    tipo = (tipo or "").lower()
    if "former" in tipo or "ex-cliente" in tipo:
        return AccountLifecycle.CHURNED
    if "customer" in tipo or "cliente" in tipo:
        return AccountLifecycle.CUSTOMER
    return AccountLifecycle.PROSPECT


def _tipo_atividade(registro: dict) -> ActivityKind:
    if registro.get("attributes", {}).get("type") == "Event":
        return ActivityKind.MEETING
    subtipo = (registro.get("TaskSubtype") or registro.get("Type") or "").lower()
    return {"call": ActivityKind.CALL, "email": ActivityKind.EMAIL, "listemail": ActivityKind.EMAIL,
            "meeting": ActivityKind.MEETING}.get(subtipo, ActivityKind.TASK)


class SalesforceAdapter(AcessoBearer, CrmAdapter):
    SISTEMA = SYSTEM

    def __init__(
        self,
        tenant_id: str,
        credenciais: dict,
        configuracao: dict | None = None,
        transport: httpx.BaseTransport | None = None,
        ao_renovar_token: Callable[[dict], None] | None = None,
    ) -> None:
        configuracao = configuracao or {}
        validar(credenciais, configuracao)
        self._tenant_id = tenant_id
        self._moeda = configuracao.get("moeda", "BRL")
        self._campo_cnpj = configuracao.get("campo_cnpj")
        self._campo_nps = configuracao.get("campo_nps")
        self._iniciar_acesso(credenciais, transport, ao_renovar_token)

    # --- HTTP + auth -------------------------------------------------------------
    def _base_url(self) -> str:
        return self._credenciais["instance_url"]

    def _app(self) -> tuple[str, str]:
        if self._credenciais.get("oauth_app") == "b2bon":
            return settings.oauth_salesforce_client_id, settings.oauth_salesforce_client_secret
        return self._credenciais.get("client_id", ""), self._credenciais.get("client_secret", "")

    def _pode_renovar(self) -> bool:
        return bool(self._credenciais.get("refresh_token") and self._app()[0])

    def _renovar_token(self) -> dict:
        client_id, client_secret = self._app()
        dados = {"grant_type": "refresh_token", "refresh_token": self._credenciais["refresh_token"], "client_id": client_id}
        if client_secret:
            dados["client_secret"] = client_secret
        login = self._credenciais.get("login_url", "https://login.salesforce.com")
        resposta = self._cliente_auth(login).post_form("/services/oauth2/token", dados)
        nova_instancia = resposta.get("instance_url", self._credenciais["instance_url"])
        if not host_permitido(nova_instancia, HOSTS_API):
            raise ErroCredencial("salesforce: renovação de token devolveu instância fora do Salesforce.")
        return {"access_token": resposta.get("access_token"), "instance_url": nova_instancia}

    def _consulta(self, soql: str, cursor: str | None) -> tuple[list[dict], str | None]:
        if cursor:
            if not cursor.startswith("/services/data/"):
                raise ValueError("Cursor Salesforce inválido.")
            resposta = self._get(cursor)
        else:
            resposta = self._get(f"/services/data/{VERSAO_API}/query", {"q": soql})
        proximo = None if resposta.get("done", True) else resposta.get("nextRecordsUrl")
        return resposta.get("records", []), proximo

    def _todos(self, soql: str) -> list[dict]:
        registros, cursor = self._consulta(soql, None)
        while cursor:
            mais, cursor = self._consulta(soql, cursor)
            registros.extend(mais)
        return registros

    def _meu(self, tenant_id: str) -> bool:
        return tenant_id == self._tenant_id

    @staticmethod
    def _onde(updated_since: datetime | None, *condicoes: str) -> str:
        todas = list(condicoes) + ([f"LastModifiedDate > {_literal_data(updated_since)}"] if updated_since else [])
        return f" WHERE {' AND '.join(todas)}" if todas else ""

    def _pagina(self, tenant_id: str, soql: str, cursor: str | None, converter) -> Page:
        if not self._meu(tenant_id):
            return Page(items=[])
        agora = datetime.now(UTC)
        registros, proximo = self._consulta(soql, cursor)
        itens = [item for item in (converter(r, agora) for r in registros) if item is not None]
        return Page(items=itens, next_cursor=proximo)

    # --- Contrato ----------------------------------------------------------------
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(system=SYSTEM, readable_entities=_LEGIVEIS, writable_entities=ESCRITAS, incremental_sync=True, webhooks=True)

    def _soql_contas(self, updated_since: datetime | None) -> str:
        campos = "Id, Name, Website, Industry, NumberOfEmployees, BillingState, Type, OwnerId, CreatedDate, LastModifiedDate"
        if self._campo_cnpj:
            campos += f", {self._campo_cnpj}"
        return f"SELECT {campos} FROM Account{self._onde(updated_since)} ORDER BY Id"

    def _organizacao(self, r: dict, agora: datetime) -> Organization:
        cnpj = re.sub(r"\D", "", str(r.get(self._campo_cnpj) or "")) if self._campo_cnpj else ""
        empregados = r.get("NumberOfEmployees")
        return Organization(
            id=cid("organization", r["Id"]), tenant_id=self._tenant_id, source=_src("Account", r["Id"], agora),
            legal_name=r["Name"], tax_id=cnpj or None, domain=_dominio(r.get("Website")), industry=r.get("Industry"),
            size=str(empregados) if empregados is not None else None, region=r.get("BillingState"),
            created_at=_data(r.get("CreatedDate")), updated_at=_data(r.get("LastModifiedDate")),
        )

    def _conta(self, r: dict, agora: datetime) -> Account:
        return Account(
            id=cid("account", r["Id"]), tenant_id=self._tenant_id, source=_src("Account", r["Id"], agora),
            organization_id=cid("organization", r["Id"]), owner_user_id=r.get("OwnerId"), lifecycle=_lifecycle(r.get("Type")),
            created_at=_data(r.get("CreatedDate")), updated_at=_data(r.get("LastModifiedDate")),
        )

    def list_organizations(self, tenant_id, cursor=None, updated_since=None, limit=100):
        return self._pagina(tenant_id, self._soql_contas(updated_since), cursor, self._organizacao)

    def list_accounts(self, tenant_id, cursor=None, updated_since=None, limit=100):
        return self._pagina(tenant_id, self._soql_contas(updated_since), cursor, self._conta)

    def list_customers(self, tenant_id, cursor=None, limit=100):
        """Salesforce não tem "cliente desde": usa a 1ª oportunidade ganha
        da conta. `churned_at` fica desconhecido (None)."""
        if not self._meu(tenant_id):
            return Page(items=[])
        agora = datetime.now(UTC)
        primeira: dict[str, str] = {}
        for r in self._todos("SELECT AccountId, CloseDate FROM Opportunity WHERE IsWon = true AND AccountId != null ORDER BY CloseDate"):
            primeira.setdefault(r["AccountId"], r["CloseDate"])
        return Page(items=[
            Customer(id=cid("customer", conta), tenant_id=self._tenant_id, source=_src("Account", conta, agora),
                     account_id=cid("account", conta), customer_since=_data(data))
            for conta, data in primeira.items()
        ])

    def _soql_contatos(self, updated_since: datetime | None = None) -> str:
        return ("SELECT Id, AccountId, Name, Title, Email, Phone, HasOptedOutOfEmail, CreatedDate, LastModifiedDate "
                f"FROM Contact{self._onde(updated_since)} ORDER BY Id")

    def _pessoa(self, r: dict, agora: datetime) -> Person:
        return Person(
            id=cid("person", r["Id"]), tenant_id=self._tenant_id, source=_src("Contact", r["Id"], agora),
            organization_id=cid("organization", r["AccountId"]) if r.get("AccountId") else None,
            full_name=r.get("Name") or "(sem nome)", job_title=r.get("Title"), email=r.get("Email"), phone=r.get("Phone"),
            # opt-out não tem data no Salesforce: usa a última alteração do contato como limite conhecido
            suppressed_at=_data(r.get("LastModifiedDate")) or agora if r.get("HasOptedOutOfEmail") else None,
            created_at=_data(r.get("CreatedDate")), updated_at=_data(r.get("LastModifiedDate")),
        )

    def _contato(self, r: dict, agora: datetime) -> Contact | None:
        if not r.get("AccountId"):
            return None
        return Contact(id=cid("contact", r["Id"]), tenant_id=self._tenant_id, source=_src("Contact", r["Id"], agora),
                       account_id=cid("account", r["AccountId"]), person_id=cid("person", r["Id"]))

    def list_people(self, tenant_id, cursor=None, updated_since=None, limit=100):
        return self._pagina(tenant_id, self._soql_contatos(updated_since), cursor, self._pessoa)

    def list_contacts(self, tenant_id, cursor=None, limit=100):
        return self._pagina(tenant_id, self._soql_contatos(), cursor, self._contato)

    def list_pipelines(self, tenant_id):
        if not self._meu(tenant_id):
            return []
        return [Pipeline(id=PIPELINE_ID, tenant_id=self._tenant_id, name="Salesforce",
                         source=SourceRef(system=SYSTEM, external_id="default", entity="OpportunityStage"))]

    def list_stages(self, tenant_id):
        if not self._meu(tenant_id):
            return []
        agora = datetime.now(UTC)
        estagios = []
        registros = self._todos("SELECT Id, ApiName, MasterLabel, SortOrder, IsClosed, IsWon FROM OpportunityStage WHERE IsActive = true ORDER BY SortOrder")
        for ordem, r in enumerate(registros):
            chave = r.get("ApiName") or r["MasterLabel"]
            tipo = StageType.WON if r.get("IsWon") else StageType.LOST if r.get("IsClosed") else StageType.OPEN
            estagios.append(PipelineStage(
                id=cid("stage", chave), tenant_id=self._tenant_id, source=_src("OpportunityStage", r["Id"], agora),
                pipeline_id=PIPELINE_ID, name=r["MasterLabel"], order=r.get("SortOrder") or ordem, stage_type=tipo,
            ))
        return estagios

    def _oportunidade(self, r: dict, agora: datetime) -> Opportunity | None:
        if not r.get("AccountId"):
            return None  # oportunidade sem conta não tem para quem ser atribuída
        status = OpportunityStatus.WON if r.get("IsWon") else OpportunityStatus.LOST if r.get("IsClosed") else OpportunityStatus.OPEN
        valor = r.get("Amount")
        probabilidade = r.get("Probability")
        return Opportunity(
            id=cid("opportunity", r["Id"]), tenant_id=self._tenant_id, source=_src("Opportunity", r["Id"], agora),
            account_id=cid("account", r["AccountId"]), owner_user_id=r.get("OwnerId"), pipeline_id=PIPELINE_ID,
            stage_id=cid("stage", r["StageName"]), name=r["Name"],
            amount=Money(amount=Decimal(str(valor)), currency=self._moeda) if valor is not None else None,
            probability=round(probabilidade) if probabilidade is not None else None, status=status,
            closed_at=_data(r.get("CloseDate")) if r.get("IsClosed") else None,
            created_at=_data(r.get("CreatedDate")), updated_at=_data(r.get("LastModifiedDate")),
        )

    def list_opportunities(self, tenant_id, cursor=None, updated_since=None, limit=100):
        soql = ("SELECT Id, AccountId, Name, Amount, Probability, StageName, IsClosed, IsWon, CloseDate, OwnerId, "
                f"CreatedDate, LastModifiedDate FROM Opportunity{self._onde(updated_since)} ORDER BY Id")
        return self._pagina(tenant_id, soql, cursor, self._oportunidade)

    # Tarefas e eventos: dois objetos, um cursor. O cursor carrega o objeto
    # da vez ("Task|<url>" / "Event|") para continuar do ponto certo.
    _SOQL_ATIVIDADES = {
        "Task": "SELECT Id, AccountId, WhatId, Subject, TaskSubtype, Type, OwnerId, CreatedDate FROM Task ORDER BY Id",
        "Event": "SELECT Id, AccountId, WhatId, Subject, Type, OwnerId, CreatedDate FROM Event ORDER BY Id",
    }

    def _atividades_brutas(self, cursor: str | None, condicao: str = "") -> tuple[list[dict], str | None]:
        objeto, _, url = (cursor or "Task|").partition("|")
        if objeto not in self._SOQL_ATIVIDADES:
            raise ValueError("Cursor Salesforce inválido.")
        soql = self._SOQL_ATIVIDADES[objeto].replace(" ORDER BY", f"{condicao} ORDER BY")
        registros, proximo = self._consulta(soql, url or None)
        if proximo:
            return registros, f"{objeto}|{proximo}"
        return registros, "Event|" if objeto == "Task" else None

    def _atividade(self, r: dict, agora: datetime) -> Activity:
        objeto = r.get("attributes", {}).get("type", "Task")
        what = r.get("WhatId") or ""
        return Activity(
            id=cid(objeto.lower(), r["Id"]), tenant_id=self._tenant_id, source=_src(objeto, r["Id"], agora),
            account_id=cid("account", r["AccountId"]) if r.get("AccountId") else None,
            opportunity_id=cid("opportunity", what) if what.startswith("006") else None,
            user_id=r.get("OwnerId"), kind=_tipo_atividade(r), source_type=r.get("TaskSubtype") or r.get("Type") or objeto,
            description=r.get("Subject") or "", created_at=_data(r.get("CreatedDate")),
        )

    def list_activities(self, tenant_id, cursor=None, limit=100):
        if not self._meu(tenant_id):
            return Page(items=[])
        agora = datetime.now(UTC)
        registros, proximo = self._atividades_brutas(cursor)
        return Page(items=[self._atividade(r, agora) for r in registros], next_cursor=proximo)

    def list_interactions(self, tenant_id, account_id=None, cursor=None, limit=100):
        """Tarefas/eventos concluídos com a conta = contato registrado
        (tipo "contato" do MAP). Reclamação/elogio não existem como
        objeto padrão no Salesforce e não são inferidos."""
        if not self._meu(tenant_id):
            return Page(items=[])
        condicao = ""
        if account_id is not None:
            sf_id = account_id.removeprefix(cid("account", ""))
            if not re.fullmatch(r"[A-Za-z0-9]{15,18}", sf_id):
                return Page(items=[])
            condicao = f" WHERE AccountId = '{sf_id}'"
        agora = datetime.now(UTC)
        registros, proximo = self._atividades_brutas(cursor, condicao)
        itens = [
            Interaction(id=cid("interaction", r["Id"]), tenant_id=self._tenant_id, source=_src(r["attributes"]["type"], r["Id"], agora),
                        account_id=cid("account", r["AccountId"]), kind="contato", description=r.get("Subject"),
                        created_at=_data(r.get("CreatedDate")))
            for r in registros if r.get("AccountId")
        ]
        return Page(items=itens, next_cursor=proximo)

    def list_cs_metrics(self, tenant_id, cursor=None, limit=100):
        """Sem objeto padrão de NPS no Salesforce: lê o campo da Account
        configurado em `campo_nps` (D-087)."""
        if not self._campo_nps:
            return Page(items=[])
        return self._pagina(tenant_id, f"SELECT Id, LastModifiedDate, {self._campo_nps} FROM Account WHERE {self._campo_nps} != null ORDER BY Id",
                            cursor, self._metrica_nps)

    def _metrica_nps(self, r: dict, agora: datetime) -> CSMetric | None:
        nota = interacoes.nota_nps(r.get(self._campo_nps))
        if nota is None:
            return None
        return CSMetric(id=cid("cs_metric", f"nps-{r['Id']}"), tenant_id=self._tenant_id, source=_src("Account", r["Id"], agora),
                        account_id=cid("account", r["Id"]), metric="NPS", value=nota, scale_max=10, collected_at=_data(r.get("LastModifiedDate")))

    def list_offers(self, tenant_id):
        if not self._meu(tenant_id):
            return []
        agora = datetime.now(UTC)
        return [
            Offer(id=cid("offer", r["Id"]), tenant_id=self._tenant_id, source=_src("Product2", r["Id"], agora),
                  name=r["Name"], category=r.get("Family"), description=r.get("Description"), active=bool(r.get("IsActive")))
            for r in self._todos("SELECT Id, Name, Family, Description, IsActive FROM Product2 ORDER BY Id")
        ]


    # --- Escrita (D-087) ----------------------------------------------------------
    def _exigir_meu(self, tenant_id: str) -> None:
        if not self._meu(tenant_id):
            raise PermissionError("Conexão de outro tenant.")

    def _primeiro_id(self, soql: str) -> str | None:
        registros, _ = self._consulta(soql, None)
        return registros[0]["Id"] if registros else None

    def _criar(self, objeto: str, campos: dict) -> str:
        resposta = self._escrever("POST", f"/services/data/{VERSAO_API}/sobjects/{objeto}", {k: v for k, v in campos.items() if v not in (None, "")})
        return str(resposta["id"])

    def _atualizar(self, objeto: str, id_: str, campos: dict) -> None:
        self._escrever("PATCH", f"/services/data/{VERSAO_API}/sobjects/{objeto}/{_sf_id(id_)}", campos)

    def garantir_empresa(self, tenant_id: str, empresa: EmpresaSaida) -> str:
        self._exigir_meu(tenant_id)
        if empresa.cnpj and self._campo_cnpj and empresa.cnpj.isdigit() and len(empresa.cnpj) == 14:
            c = empresa.cnpj
            formatado = f"{c[:2]}.{c[2:5]}.{c[5:8]}/{c[8:12]}-{c[12:]}"
            existente = self._primeiro_id(f"SELECT Id FROM Account WHERE {self._campo_cnpj} IN ('{c}', '{formatado}') LIMIT 1")
            if existente:
                return existente
        if empresa.dominio and _DOMINIO.match(empresa.dominio):
            existente = self._primeiro_id(f"SELECT Id FROM Account WHERE Website LIKE '%{empresa.dominio}%' LIMIT 1")
            if existente:
                return existente
        campos = {"Name": empresa.nome, "Website": empresa.dominio, "OwnerId": _sf_id(empresa.dono_externo_id) if empresa.dono_externo_id else None}
        if self._campo_cnpj:
            campos[self._campo_cnpj] = empresa.cnpj
        return self._criar("Account", campos)

    def garantir_pessoa(self, tenant_id: str, pessoa: PessoaSaida) -> str:
        self._exigir_meu(tenant_id)
        if pessoa.email:
            existente = self._primeiro_id(f"SELECT Id FROM Contact WHERE Email = '{_literal(pessoa.email.lower())}' LIMIT 1")
            if existente:
                return existente
        primeiro, _, resto = pessoa.nome.partition(" ")
        return self._criar("Contact", {
            "FirstName": primeiro if resto else None, "LastName": resto or primeiro, "Email": pessoa.email, "Phone": pessoa.telefone,
            "Title": pessoa.cargo, "AccountId": _sf_id(pessoa.empresa_id) if pessoa.empresa_id else None,
            "OwnerId": _sf_id(pessoa.dono_externo_id) if pessoa.dono_externo_id else None,
        })

    def registrar_atividade(self, tenant_id: str, atividade: AtividadeSaida) -> str:
        self._exigir_meu(tenant_id)
        what = atividade.negocio_id or atividade.empresa_id
        comuns = {"WhatId": _sf_id(what) if what else None, "WhoId": _sf_id(atividade.pessoa_id) if atividade.pessoa_id else None,
                  "OwnerId": _sf_id(atividade.dono_externo_id) if atividade.dono_externo_id else None}
        canal = {TipoAtividadeSaida.WHATSAPP: "[WhatsApp] ", TipoAtividadeSaida.LINKEDIN: "[LinkedIn] ", TipoAtividadeSaida.EMAIL: "[E-mail] ",
                 TipoAtividadeSaida.LIGACAO: "[Ligação] ", TipoAtividadeSaida.NOTA: "[Nota] "}.get(atividade.tipo, "")
        if atividade.tipo == TipoAtividadeSaida.REUNIAO:
            inicio = atividade.ocorrida_em.astimezone(UTC)
            fim = inicio + timedelta(minutes=atividade.duracao_minutos or 30)
            return self._criar("Event", {"Subject": atividade.assunto[:255], "Description": atividade.descricao,
                                         "StartDateTime": _literal_data(inicio), "EndDateTime": _literal_data(fim), **comuns})
        return self._criar("Task", {"Subject": f"{canal}{atividade.assunto}"[:255], "Description": atividade.descricao,
                                    "ActivityDate": atividade.ocorrida_em.astimezone(UTC).date().isoformat(), "Status": "Completed", **comuns})

    def criar_negocio(self, tenant_id: str, negocio: NegocioSaida) -> str:
        self._exigir_meu(tenant_id)
        if negocio.previsao_fechamento is None:
            raise OperacaoNaoSuportada("Salesforce exige data de fechamento: configure o prazo na conexão.")
        oportunidade = self._criar("Opportunity", {
            "Name": negocio.nome, "AccountId": _sf_id(negocio.empresa_id), "StageName": negocio.estagio_id,
            "CloseDate": negocio.previsao_fechamento.isoformat(),
            "OwnerId": _sf_id(negocio.dono_externo_id) if negocio.dono_externo_id else None,
        })
        if negocio.pessoa_id:
            try:  # papel do contato é complemento: falhar aqui não pode duplicar a oportunidade
                self._criar("OpportunityContactRole", {"OpportunityId": oportunidade, "ContactId": _sf_id(negocio.pessoa_id), "IsPrimary": True})
            except ErroConector:
                pass
        return oportunidade

    def criar_tarefa(self, tenant_id: str, tarefa: TarefaSaida) -> str:
        self._exigir_meu(tenant_id)
        return self._criar("Task", {
            "Subject": tarefa.assunto[:255], "Description": tarefa.descricao, "ActivityDate": tarefa.vencimento.isoformat(),
            "Status": "Not Started", "Priority": "High", "WhatId": _sf_id(tarefa.empresa_id) if tarefa.empresa_id else None,
            "OwnerId": _sf_id(tarefa.dono_externo_id) if tarefa.dono_externo_id else None,
        })

    def marcar_optout(self, tenant_id: str, pessoa_id: str, campos: CamposProprios) -> None:
        self._exigir_meu(tenant_id)
        valores: dict = {"HasOptedOutOfEmail": True}
        if campos.optout:
            valores[campos.optout] = True
        self._atualizar("Contact", pessoa_id, valores)

    def gravar_sinais_conta(self, tenant_id: str, sinais: SinaisContaSaida, campos: CamposProprios) -> None:
        self._exigir_meu(tenant_id)
        valores: dict = {}
        if campos.score_risco:
            valores[campos.score_risco] = round(sinais.score_risco, 1)
        if campos.nivel_risco:
            valores[campos.nivel_risco] = sinais.nivel_risco
        if not valores:
            raise OperacaoNaoSuportada("Nenhum campo de risco configurado.")
        self._atualizar("Account", sinais.empresa_id, valores)


_SF_ID = re.compile(r"^[A-Za-z0-9]{15}([A-Za-z0-9]{3})?$")
_DOMINIO = re.compile(r"^[a-z0-9][a-z0-9.\-]{0,252}$")


def _sf_id(valor: str) -> str:
    """Id vai para URL e SOQL: só o formato de id do Salesforce."""
    if not _SF_ID.match(str(valor)):
        raise ValueError("Id Salesforce inválido.")
    return str(valor)


def _literal(valor: str) -> str:
    """Literal SOQL: escapa barra invertida e aspas (anti-injeção)."""
    return valor.replace("\\", "\\\\").replace("'", "\\'")


def fabrica(db, conexao) -> SalesforceAdapter:
    return SalesforceAdapter(conexao.tenant_id, json.loads(conexao.credenciais or "{}"), conexao.configuracao or {},
                             ao_renovar_token=persistidor(db, conexao))
