"""Conector HubSpot ↔ modelo canônico (Fase 13, conector 2 de 4; escrita D-087).

Leitura via CRM API v3 (`https://api.hubapi.com`, host fixo:
nada que o tenant informe vira URL). Listagem por `after`; incremental
pela Search API (`hs_lastmodifieddate`/`lastmodifieddate` > limite);
associações negócio → empresa pela Associations API v4. Mapeamento em
`docs/b2bon/14_INTEGRATION_HUB.md` §HubSpot. BETA (D-041).

Escrita (D-087): empresas/contatos procurados antes de criar (CNPJ →
domínio; e-mail) e nunca alterados; negócios, notas, reuniões, e-mails e
tarefas criados com associações v4 (ids de tipo HUBSPOT_DEFINED); sinais do
MAP e opt-out em propriedades PRÓPRIAS (`b2bon_*`, criadas por
`preparar_campos`).

Credenciais: `access_token` (token de Private App ou OAuth) e,
opcionalmente, `refresh_token` + `client_id` + `client_secret` (app OAuth),
ou `oauth_app: "b2bon"` quando conectado pelo app OAuth da B2B ON (client
id/secret vêm da configuração do servidor, nunca do tenant).
Configuração: `moeda` (usada quando o negócio não traz
`deal_currency_code`) e `campo_cnpj` (propriedade customizada da empresa).
"""

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation

import httpx

from app.contexts.integrations.adapters import interacoes
from app.contexts.integrations.adapters.http_base import AcessoBearer, ErroConector, persistidor
from app.contexts.integrations.contract import (
    ESCRITAS,
    AdapterCapabilities,
    AtividadeSaida,
    CamposProprios,
    CrmAdapter,
    EmpresaSaida,
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

SYSTEM = "hubspot"
API = "https://api.hubapi.com"
_PROPRIEDADE = re.compile(r"^[a-z][a-z0-9_]{0,99}$")
_MOEDA = re.compile(r"^[A-Z]{3}$")
_CURSOR = re.compile(r"^[A-Za-z0-9_\-=]{1,200}$")
_LIMITE = 100

_LEGIVEIS = frozenset({
    "organizations", "accounts", "customers", "people", "contacts", "pipelines", "stages",
    "opportunities", "activities", "interactions", "offers",
})

_PROPS_EMPRESA = ["name", "domain", "industry", "numberofemployees", "state", "lifecyclestage", "hubspot_owner_id",
                  "hs_lifecyclestage_customer_date", "createdate", "hs_lastmodifieddate"]
_PROPS_CONTATO = ["firstname", "lastname", "email", "jobtitle", "phone", "associatedcompanyid", "hs_email_optout",
                  "createdate", "lastmodifieddate"]
_PROPS_NEGOCIO = ["dealname", "amount", "dealstage", "pipeline", "closedate", "hubspot_owner_id", "hs_is_closed",
                  "hs_is_closed_won", "hs_deal_stage_probability", "deal_currency_code", "createdate", "hs_lastmodifieddate"]
# Engajamentos: objeto → (propriedade do título, tipo canônico)
_ENGAJAMENTOS = {
    "calls": ("hs_call_title", ActivityKind.CALL),
    "emails": ("hs_email_subject", ActivityKind.EMAIL),
    "meetings": ("hs_meeting_title", ActivityKind.MEETING),
    "tasks": ("hs_task_subject", ActivityKind.TASK),
    "notes": ("hs_note_body", ActivityKind.NOTE),
}
_CICLO = {
    "customer": AccountLifecycle.CUSTOMER, "evangelist": AccountLifecycle.CUSTOMER,
    "subscriber": AccountLifecycle.LEAD, "lead": AccountLifecycle.LEAD, "marketingqualifiedlead": AccountLifecycle.LEAD,
    "salesqualifiedlead": AccountLifecycle.QUALIFIED, "opportunity": AccountLifecycle.QUALIFIED,
}


# Associações v4 (associationCategory HUBSPOT_DEFINED): origem → destino → typeId.
ASSOCIACOES = {
    ("contacts", "companies"): 279, ("deals", "companies"): 341, ("deals", "contacts"): 3,
    ("notes", "companies"): 190, ("notes", "contacts"): 202, ("notes", "deals"): 214,
    ("meetings", "companies"): 188, ("meetings", "contacts"): 200, ("meetings", "deals"): 212,
    ("emails", "companies"): 186, ("emails", "contacts"): 198, ("emails", "deals"): 210,
    ("calls", "companies"): 182, ("calls", "contacts"): 194, ("calls", "deals"): 206,
    ("tasks", "companies"): 192, ("tasks", "contacts"): 204, ("tasks", "deals"): 216,
}
# Atividade canônica → objeto de engajamento. WhatsApp/LinkedIn viram nota
# (o objeto "communications" depende de recurso do portal).
_OBJETO_ATIVIDADE = {TipoAtividadeSaida.EMAIL: "emails", TipoAtividadeSaida.LIGACAO: "calls", TipoAtividadeSaida.REUNIAO: "meetings"}
CAMPOS_PADRAO = CamposProprios(score_risco="b2bon_score_risco", nivel_risco="b2bon_nivel_risco", optout="b2bon_opt_out")


def validar(credenciais: dict, configuracao: dict) -> None:
    app_b2bon = credenciais.get("oauth_app") == "b2bon"
    if not credenciais.get("access_token") and not credenciais.get("refresh_token"):
        raise ValueError("Informe o access_token (Private App) ou o refresh_token do app OAuth.")
    if credenciais.get("refresh_token") and not app_b2bon and not (credenciais.get("client_id") and credenciais.get("client_secret")):
        raise ValueError("refresh_token exige client_id e client_secret do app OAuth.")
    if "oauth_app" in credenciais and not app_b2bon:
        raise ValueError("oauth_app inválido.")
    extras = set(credenciais) - {"access_token", "refresh_token", "client_id", "client_secret", "oauth_app"}
    if extras:
        raise ValueError(f"Credenciais não reconhecidas: {sorted(extras)}")
    campo = configuracao.get("campo_cnpj")
    if campo is not None and not (isinstance(campo, str) and _PROPRIEDADE.match(campo)):
        raise ValueError("campo_cnpj deve ser o nome interno de uma propriedade (ex.: cnpj).")
    nps = configuracao.get("campo_nps")
    if nps is not None and not (isinstance(nps, str) and _PROPRIEDADE.match(nps)):
        raise ValueError("campo_nps deve ser o nome/id do campo com a nota NPS (0–10) da empresa.")
    moeda = configuracao.get("moeda", "BRL")
    if not (isinstance(moeda, str) and _MOEDA.match(moeda)):
        raise ValueError("moeda deve ser um código ISO 4217 (ex.: BRL).")


def cid(entidade: str, id_: str) -> str:
    return canonical_id(SYSTEM, entidade, id_)


def _src(entidade: str, id_: str, agora: datetime) -> SourceRef:
    return SourceRef(system=SYSTEM, external_id=str(id_), entity=entidade, fetched_at=agora)


def _data(valor: str | None) -> datetime | None:
    if not valor:
        return None
    if valor.isdigit():  # alguns campos de data vêm em epoch ms
        return datetime.fromtimestamp(int(valor) / 1000, tz=UTC)
    if len(valor) == 10:
        return datetime.fromisoformat(valor).replace(tzinfo=UTC)
    return datetime.fromisoformat(valor.replace("Z", "+00:00"))


def _epoch_ms(momento: datetime) -> str:
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=UTC)
    return str(int(momento.timestamp() * 1000))


def _verdadeiro(valor) -> bool:
    return str(valor).lower() == "true"


def _decimal(valor: str | None) -> Decimal | None:
    if valor in (None, ""):
        return None
    try:
        return Decimal(str(valor))
    except InvalidOperation:
        return None


def _checar_cursor(cursor: str | None) -> str | None:
    if cursor is not None and not _CURSOR.match(cursor):
        raise ValueError("Cursor HubSpot inválido.")
    return cursor


class HubSpotAdapter(AcessoBearer, CrmAdapter):
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
        self._interacoes: dict[str, list[Interaction]] | None = None
        self._iniciar_acesso(credenciais, transport, ao_renovar_token)

    # --- HTTP + auth -------------------------------------------------------------
    def _base_url(self) -> str:
        return API

    def _app(self) -> tuple[str, str]:
        if self._credenciais.get("oauth_app") == "b2bon":
            return settings.oauth_hubspot_client_id, settings.oauth_hubspot_client_secret
        return self._credenciais.get("client_id", ""), self._credenciais.get("client_secret", "")

    def _pode_renovar(self) -> bool:
        return bool(self._credenciais.get("refresh_token") and all(self._app()))

    def _renovar_token(self) -> dict:
        client_id, client_secret = self._app()
        resposta = self._cliente_auth(API).post_form("/oauth/v1/token", {
            "grant_type": "refresh_token", "refresh_token": self._credenciais["refresh_token"],
            "client_id": client_id, "client_secret": client_secret,
        })
        mudancas = {"access_token": resposta.get("access_token")}
        if resposta.get("refresh_token"):
            mudancas["refresh_token"] = resposta["refresh_token"]
        return mudancas

    def _meu(self, tenant_id: str) -> bool:
        return tenant_id == self._tenant_id

    def _objetos(self, objeto: str, propriedades: list[str], cursor: str | None, updated_since: datetime | None = None,
                 campo_modificacao: str = "hs_lastmodifieddate", associacoes: str | None = None) -> tuple[list[dict], str | None]:
        cursor = _checar_cursor(cursor)
        if updated_since is not None:
            corpo = {
                "filterGroups": [{"filters": [{"propertyName": campo_modificacao, "operator": "GT", "value": _epoch_ms(updated_since)}]}],
                "sorts": [{"propertyName": campo_modificacao, "direction": "ASCENDING"}],
                "properties": propriedades, "limit": _LIMITE,
            }
            if cursor:
                corpo["after"] = cursor
            resposta = self._post(f"/crm/v3/objects/{objeto}/search", corpo)
        else:
            params = {"limit": _LIMITE, "properties": ",".join(propriedades), "archived": "false"}
            if cursor:
                params["after"] = cursor
            if associacoes:
                params["associations"] = associacoes
            resposta = self._get(f"/crm/v3/objects/{objeto}", params)
        proximo = (resposta.get("paging") or {}).get("next", {}).get("after")
        return resposta.get("results", []), proximo

    def _todos(self, objeto: str, propriedades: list[str], **kwargs) -> list[dict]:
        registros, cursor = self._objetos(objeto, propriedades, None, **kwargs)
        while cursor:
            mais, cursor = self._objetos(objeto, propriedades, cursor, **kwargs)
            registros.extend(mais)
        return registros

    def _pagina(self, tenant_id: str, converter, objeto: str, propriedades: list[str], cursor, **kwargs) -> Page:
        if not self._meu(tenant_id):
            return Page(items=[])
        agora = datetime.now(UTC)
        registros, proximo = self._objetos(objeto, propriedades, cursor, **kwargs)
        return Page(items=[i for i in (converter(r, agora) for r in registros) if i is not None], next_cursor=proximo)

    # --- Contrato ----------------------------------------------------------------
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(system=SYSTEM, readable_entities=_LEGIVEIS, writable_entities=ESCRITAS, incremental_sync=True, webhooks=True)

    def _props_empresa(self) -> list[str]:
        return _PROPS_EMPRESA + [c for c in (self._campo_cnpj, self._campo_nps) if c]

    def _organizacao(self, r: dict, agora: datetime) -> Organization:
        p = r.get("properties", {})
        cnpj = re.sub(r"\D", "", str(p.get(self._campo_cnpj) or "")) if self._campo_cnpj else ""
        return Organization(
            id=cid("organization", r["id"]), tenant_id=self._tenant_id, source=_src("company", r["id"], agora),
            legal_name=p.get("name") or p.get("domain") or f"Empresa {r['id']}", tax_id=cnpj or None,
            domain=(p.get("domain") or "").removeprefix("www.") or None, industry=p.get("industry"),
            size=p.get("numberofemployees") or None, region=p.get("state"),
            created_at=_data(r.get("createdAt")), updated_at=_data(r.get("updatedAt")),
        )

    def _conta(self, r: dict, agora: datetime) -> Account:
        p = r.get("properties", {})
        return Account(
            id=cid("account", r["id"]), tenant_id=self._tenant_id, source=_src("company", r["id"], agora),
            organization_id=cid("organization", r["id"]), owner_user_id=p.get("hubspot_owner_id") or None,
            lifecycle=_CICLO.get((p.get("lifecyclestage") or "").lower(), AccountLifecycle.PROSPECT),
            created_at=_data(r.get("createdAt")), updated_at=_data(r.get("updatedAt")),
        )

    def list_organizations(self, tenant_id, cursor=None, updated_since=None, limit=100):
        return self._pagina(tenant_id, self._organizacao, "companies", self._props_empresa(), cursor, updated_since=updated_since)

    def list_accounts(self, tenant_id, cursor=None, updated_since=None, limit=100):
        return self._pagina(tenant_id, self._conta, "companies", self._props_empresa(), cursor, updated_since=updated_since)

    def list_customers(self, tenant_id, cursor=None, limit=100):
        """Empresa em estágio cliente com data de entrada conhecida. Sem a
        data (`hs_lifecyclestage_customer_date`), não vira Customer: a data
        não é inventada. `churned_at` fica desconhecido."""
        if not self._meu(tenant_id):
            return Page(items=[])
        agora = datetime.now(UTC)
        registros, proximo = self._objetos("companies", _PROPS_EMPRESA, cursor)
        itens = []
        for r in registros:
            p = r.get("properties", {})
            desde = _data(p.get("hs_lifecyclestage_customer_date"))
            if _CICLO.get((p.get("lifecyclestage") or "").lower()) == AccountLifecycle.CUSTOMER and desde:
                itens.append(Customer(id=cid("customer", r["id"]), tenant_id=self._tenant_id, source=_src("company", r["id"], agora),
                                      account_id=cid("account", r["id"]), customer_since=desde))
        return Page(items=itens, next_cursor=proximo)

    def _pessoa(self, r: dict, agora: datetime) -> Person:
        p = r.get("properties", {})
        nome = " ".join(x for x in (p.get("firstname"), p.get("lastname")) if x) or p.get("email") or "(sem nome)"
        empresa = p.get("associatedcompanyid")
        return Person(
            id=cid("person", r["id"]), tenant_id=self._tenant_id, source=_src("contact", r["id"], agora),
            organization_id=cid("organization", empresa) if empresa else None, full_name=nome, job_title=p.get("jobtitle"),
            email=p.get("email"), phone=p.get("phone"),
            # opt-out sem data própria: última alteração do contato é o limite conhecido
            suppressed_at=(_data(r.get("updatedAt")) or agora) if _verdadeiro(p.get("hs_email_optout")) else None,
            created_at=_data(r.get("createdAt")), updated_at=_data(r.get("updatedAt")),
        )

    def _contato(self, r: dict, agora: datetime) -> Contact | None:
        empresa = r.get("properties", {}).get("associatedcompanyid")
        if not empresa:
            return None
        return Contact(id=cid("contact", r["id"]), tenant_id=self._tenant_id, source=_src("contact", r["id"], agora),
                       account_id=cid("account", empresa), person_id=cid("person", r["id"]))

    def list_people(self, tenant_id, cursor=None, updated_since=None, limit=100):
        return self._pagina(tenant_id, self._pessoa, "contacts", _PROPS_CONTATO, cursor, updated_since=updated_since,
                            campo_modificacao="lastmodifieddate")

    def list_contacts(self, tenant_id, cursor=None, limit=100):
        return self._pagina(tenant_id, self._contato, "contacts", _PROPS_CONTATO, cursor)

    def _pipelines_brutos(self) -> list[dict]:
        return self._get("/crm/v3/pipelines/deals").get("results", [])

    def list_pipelines(self, tenant_id):
        if not self._meu(tenant_id):
            return []
        agora = datetime.now(UTC)
        return [Pipeline(id=cid("pipeline", p["id"]), tenant_id=self._tenant_id, source=_src("pipeline", p["id"], agora), name=p["label"])
                for p in self._pipelines_brutos()]

    def list_stages(self, tenant_id):
        if not self._meu(tenant_id):
            return []
        agora = datetime.now(UTC)
        estagios = []
        for pipeline in self._pipelines_brutos():
            for ordem, e in enumerate(sorted(pipeline.get("stages", []), key=lambda e: e.get("displayOrder", 0))):
                meta = e.get("metadata", {})
                fechado = _verdadeiro(meta.get("isClosed"))
                probabilidade = _decimal(meta.get("probability"))
                tipo = StageType.OPEN if not fechado else StageType.WON if probabilidade == 1 else StageType.LOST
                estagios.append(PipelineStage(
                    id=cid("stage", e["id"]), tenant_id=self._tenant_id, source=_src("pipeline_stage", e["id"], agora),
                    pipeline_id=cid("pipeline", pipeline["id"]), name=e["label"], order=ordem, stage_type=tipo,
                ))
        return estagios

    def _empresas_dos_negocios(self, ids: list[str]) -> dict[str, str]:
        """Empresa associada a cada negócio (a primeira, se houver várias)."""
        if not ids:
            return {}
        resposta = self._post("/crm/v4/associations/deals/companies/batch/read", {"inputs": [{"id": i} for i in ids]})
        return {str(r["from"]["id"]): str(r["to"][0]["toObjectId"]) for r in resposta.get("results", []) if r.get("to")}

    def list_opportunities(self, tenant_id, cursor=None, updated_since=None, limit=100):
        if not self._meu(tenant_id):
            return Page(items=[])
        agora = datetime.now(UTC)
        registros, proximo = self._objetos("deals", _PROPS_NEGOCIO, cursor, updated_since=updated_since)
        empresas = self._empresas_dos_negocios([r["id"] for r in registros])
        itens = []
        for r in registros:
            empresa = empresas.get(str(r["id"]))
            if not empresa:
                continue  # negócio sem empresa não tem conta para ser atribuído
            p = r.get("properties", {})
            ganho, fechado = _verdadeiro(p.get("hs_is_closed_won")), _verdadeiro(p.get("hs_is_closed"))
            status = OpportunityStatus.WON if ganho else OpportunityStatus.LOST if fechado else OpportunityStatus.OPEN
            valor = _decimal(p.get("amount"))
            probabilidade = _decimal(p.get("hs_deal_stage_probability"))
            itens.append(Opportunity(
                id=cid("opportunity", r["id"]), tenant_id=self._tenant_id, source=_src("deal", r["id"], agora),
                account_id=cid("account", empresa), owner_user_id=p.get("hubspot_owner_id") or None,
                pipeline_id=cid("pipeline", p.get("pipeline") or "default"), stage_id=cid("stage", p.get("dealstage") or ""),
                name=p.get("dealname") or f"Negócio {r['id']}",
                amount=Money(amount=valor, currency=p.get("deal_currency_code") or self._moeda) if valor is not None else None,
                probability=round(probabilidade * 100) if probabilidade is not None else None, status=status,
                closed_at=_data(p.get("closedate")) if fechado else None,
                created_at=_data(r.get("createdAt")), updated_at=_data(r.get("updatedAt")),
            ))
        return Page(items=itens, next_cursor=proximo)

    # Engajamentos: cinco objetos, um cursor ("calls|<after>").
    def _engajamentos(self, cursor: str | None) -> tuple[str, list[dict], str | None]:
        objeto, _, depois = (cursor or "calls|").partition("|")
        if objeto not in _ENGAJAMENTOS:
            raise ValueError("Cursor HubSpot inválido.")
        titulo = _ENGAJAMENTOS[objeto][0]
        registros, proximo = self._objetos(objeto, [titulo, "hs_timestamp", "hubspot_owner_id"], depois or None,
                                           associacoes="companies,deals")
        if proximo:
            return objeto, registros, f"{objeto}|{proximo}"
        ordem = list(_ENGAJAMENTOS)
        seguinte = ordem.index(objeto) + 1
        return objeto, registros, f"{ordem[seguinte]}|" if seguinte < len(ordem) else None

    @staticmethod
    def _associado(r: dict, tipo: str) -> str | None:
        resultados = (r.get("associations") or {}).get(tipo, {}).get("results", [])
        return str(resultados[0]["id"]) if resultados else None

    def _atividade(self, objeto: str, r: dict, agora: datetime) -> Activity:
        p = r.get("properties", {})
        titulo, tipo = _ENGAJAMENTOS[objeto]
        empresa, negocio = self._associado(r, "companies"), self._associado(r, "deals")
        return Activity(
            id=cid(objeto.removesuffix("s"), r["id"]), tenant_id=self._tenant_id, source=_src(objeto, r["id"], agora),
            account_id=cid("account", empresa) if empresa else None, opportunity_id=cid("opportunity", negocio) if negocio else None,
            user_id=p.get("hubspot_owner_id") or None, kind=tipo, source_type=objeto,
            description=re.sub(r"<[^>]+>", " ", p.get(titulo) or "").strip()[:500],
            created_at=_data(p.get("hs_timestamp")) or _data(r.get("createdAt")),
        )

    def list_activities(self, tenant_id, cursor=None, limit=100):
        if not self._meu(tenant_id):
            return Page(items=[])
        agora = datetime.now(UTC)
        objeto, registros, proximo = self._engajamentos(cursor)
        return Page(items=[self._atividade(objeto, r, agora) for r in registros], next_cursor=proximo)

    def _todas_interacoes(self) -> dict[str, list[Interaction]]:
        """Engajamentos com empresa = contato registrado (tipo "contato" do
        MAP). Lidos uma vez por instância: o MAP pergunta conta a conta."""
        if self._interacoes is None:
            agora = datetime.now(UTC)
            por_conta: dict[str, list[Interaction]] = {}
            cursor = None
            while True:
                objeto, registros, cursor = self._engajamentos(cursor)
                for r in registros:
                    atividade = self._atividade(objeto, r, agora)
                    if atividade.account_id:
                        por_conta.setdefault(atividade.account_id, []).append(Interaction(
                            id=cid("interaction", f"{objeto}-{r['id']}"), tenant_id=self._tenant_id, source=atividade.source,
                            account_id=atividade.account_id, kind="contato", description=atividade.description or None,
                            created_at=atividade.created_at))
                if not cursor:
                    break
            self._interacoes = por_conta
        return self._interacoes

    def list_interactions(self, tenant_id, account_id=None, cursor=None, limit=100):
        if not self._meu(tenant_id):
            return Page(items=[])
        todas = self._todas_interacoes()
        if account_id is not None:
            return Page(items=list(todas.get(account_id, [])))
        return Page(items=[i for itens in todas.values() for i in itens])

    def list_cs_metrics(self, tenant_id, cursor=None, limit=100):
        """NPS da empresa num campo configurado (`campo_nps`, D-087). As
        pesquisas do Service Hub não são lidas: o campo é a fonte única."""
        if not self._campo_nps:
            return Page(items=[])
        return self._pagina(tenant_id, self._metrica_nps, "companies", self._props_empresa(), cursor)

    def _metrica_nps(self, r: dict, agora: datetime) -> CSMetric | None:
        nota = interacoes.nota_nps(r.get("properties", {}).get(self._campo_nps))
        if nota is None:
            return None
        return CSMetric(id=cid("cs_metric", f"nps-{r['id']}"), tenant_id=self._tenant_id, source=_src("company", r["id"], agora),
                        account_id=cid("account", r["id"]), metric="NPS", value=nota, scale_max=10, collected_at=_data(r.get("updatedAt")))

    def list_offers(self, tenant_id):
        if not self._meu(tenant_id):
            return []
        agora = datetime.now(UTC)
        return [
            Offer(id=cid("offer", r["id"]), tenant_id=self._tenant_id, source=_src("product", r["id"], agora),
                  name=r.get("properties", {}).get("name") or f"Produto {r['id']}", description=r.get("properties", {}).get("description"))
            for r in self._todos("products", ["name", "description"])
        ]


    # --- Escrita (D-087) ----------------------------------------------------------
    def _exigir_meu(self, tenant_id: str) -> None:
        if not self._meu(tenant_id):
            raise PermissionError("Conexão de outro tenant.")

    def _buscar(self, objeto: str, propriedade: str, valor: str) -> str | None:
        resposta = self._post(f"/crm/v3/objects/{objeto}/search", {
            "filterGroups": [{"filters": [{"propertyName": propriedade, "operator": "EQ", "value": valor}]}],
            "properties": [propriedade], "limit": 1,
        })
        resultados = resposta.get("results") or []
        return str(resultados[0]["id"]) if resultados else None

    @staticmethod
    def _associar(origem: str, alvos: dict[str, str | None]) -> list[dict]:
        return [{"to": {"id": alvo}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": ASSOCIACOES[(origem, destino)]}]}
                for destino, alvo in alvos.items() if alvo]

    def _criar(self, objeto: str, propriedades: dict, associacoes: list[dict] | None = None) -> str:
        corpo: dict = {"properties": {k: v for k, v in propriedades.items() if v not in (None, "")}}
        if associacoes:
            corpo["associations"] = associacoes
        return str(self._escrever("POST", f"/crm/v3/objects/{objeto}", corpo)["id"])

    def garantir_empresa(self, tenant_id: str, empresa: EmpresaSaida) -> str:
        self._exigir_meu(tenant_id)
        if empresa.cnpj and self._campo_cnpj:
            existente = self._buscar("companies", self._campo_cnpj, empresa.cnpj)
            if existente:
                return existente
        if empresa.dominio:
            existente = self._buscar("companies", "domain", empresa.dominio)
            if existente:
                return existente
        propriedades = {"name": empresa.nome, "domain": empresa.dominio, "hubspot_owner_id": empresa.dono_externo_id}
        if self._campo_cnpj:
            propriedades[self._campo_cnpj] = empresa.cnpj
        return self._criar("companies", propriedades)

    def garantir_pessoa(self, tenant_id: str, pessoa: PessoaSaida) -> str:
        self._exigir_meu(tenant_id)
        if pessoa.email:
            existente = self._buscar("contacts", "email", pessoa.email.lower())
            if existente:
                return existente
        primeiro, _, resto = pessoa.nome.partition(" ")
        return self._criar("contacts", {
            "firstname": primeiro, "lastname": resto, "email": pessoa.email, "phone": pessoa.telefone, "jobtitle": pessoa.cargo,
            "hubspot_owner_id": pessoa.dono_externo_id,
        }, self._associar("contacts", {"companies": pessoa.empresa_id}))

    def registrar_atividade(self, tenant_id: str, atividade: AtividadeSaida) -> str:
        self._exigir_meu(tenant_id)
        objeto = _OBJETO_ATIVIDADE.get(atividade.tipo, "notes")
        quando = _epoch_ms(atividade.ocorrida_em)
        alvos = {"companies": atividade.empresa_id, "contacts": atividade.pessoa_id, "deals": atividade.negocio_id}
        dono = atividade.dono_externo_id
        if objeto == "emails":
            props = {"hs_timestamp": quando, "hs_email_direction": "EMAIL", "hs_email_status": "SENT",
                     "hs_email_subject": atividade.assunto, "hs_email_text": atividade.descricao, "hubspot_owner_id": dono}
        elif objeto == "calls":
            props = {"hs_timestamp": quando, "hs_call_title": atividade.assunto, "hs_call_body": atividade.descricao, "hubspot_owner_id": dono}
        elif objeto == "meetings":
            fim = atividade.ocorrida_em + timedelta(minutes=atividade.duracao_minutos or 30)
            props = {"hs_timestamp": quando, "hs_meeting_title": atividade.assunto, "hs_meeting_body": atividade.descricao,
                     "hs_meeting_start_time": quando, "hs_meeting_end_time": _epoch_ms(fim), "hubspot_owner_id": dono}
        else:
            canal = {TipoAtividadeSaida.WHATSAPP: "WhatsApp", TipoAtividadeSaida.LINKEDIN: "LinkedIn"}.get(atividade.tipo)
            corpo = f"[{canal}] {atividade.assunto}\n\n{atividade.descricao}" if canal else f"{atividade.assunto}\n\n{atividade.descricao}"
            props = {"hs_timestamp": quando, "hs_note_body": corpo.strip(), "hubspot_owner_id": dono}
        return self._criar(objeto, props, self._associar(objeto, alvos))

    def criar_negocio(self, tenant_id: str, negocio: NegocioSaida) -> str:
        self._exigir_meu(tenant_id)
        return self._criar("deals", {
            "dealname": negocio.nome, "pipeline": negocio.pipeline_id or "default", "dealstage": negocio.estagio_id,
            "closedate": negocio.previsao_fechamento.isoformat() if negocio.previsao_fechamento else None,
            "hubspot_owner_id": negocio.dono_externo_id,
        }, self._associar("deals", {"companies": negocio.empresa_id, "contacts": negocio.pessoa_id}))

    def criar_tarefa(self, tenant_id: str, tarefa: TarefaSaida) -> str:
        self._exigir_meu(tenant_id)
        vencimento = datetime.combine(tarefa.vencimento, datetime.min.time(), tzinfo=UTC) + timedelta(hours=12)
        return self._criar("tasks", {
            "hs_timestamp": _epoch_ms(vencimento), "hs_task_subject": tarefa.assunto, "hs_task_body": tarefa.descricao,
            "hs_task_status": "NOT_STARTED", "hs_task_priority": "HIGH", "hubspot_owner_id": tarefa.dono_externo_id,
        }, self._associar("tasks", {"companies": tarefa.empresa_id}))

    def marcar_optout(self, tenant_id: str, pessoa_id: str, campos: CamposProprios) -> None:
        self._exigir_meu(tenant_id)
        campo = campos.optout or CAMPOS_PADRAO.optout
        self._escrever("PATCH", f"/crm/v3/objects/contacts/{_id_seguro(pessoa_id)}", {"properties": {campo: "true"}})

    def gravar_sinais_conta(self, tenant_id: str, sinais: SinaisContaSaida, campos: CamposProprios) -> None:
        self._exigir_meu(tenant_id)
        propriedades = {}
        if campos.score_risco:
            propriedades[campos.score_risco] = str(round(sinais.score_risco, 1))
        if campos.nivel_risco:
            propriedades[campos.nivel_risco] = sinais.nivel_risco
        if not propriedades:
            raise OperacaoNaoSuportada("Nenhum campo de risco configurado.")
        self._escrever("PATCH", f"/crm/v3/objects/companies/{_id_seguro(sinais.empresa_id)}", {"properties": propriedades})

    def preparar_campos(self, tenant_id: str) -> CamposProprios:
        """Cria as propriedades `b2bon_*` (já existentes = 409, tudo bem)."""
        self._exigir_meu(tenant_id)
        definicoes = [
            ("companies", {"name": CAMPOS_PADRAO.score_risco, "label": "B2B ON — score de risco", "type": "number", "fieldType": "number",
                           "groupName": "companyinformation", "description": "Risco de churn calculado pelo B2B ON MAP (0–100)."}),
            ("companies", {"name": CAMPOS_PADRAO.nivel_risco, "label": "B2B ON — nível de risco", "type": "string", "fieldType": "text",
                           "groupName": "companyinformation", "description": "saudavel | atencao | critico (B2B ON MAP)."}),
            ("contacts", {"name": CAMPOS_PADRAO.optout, "label": "B2B ON — opt-out", "type": "enumeration", "fieldType": "booleancheckbox",
                          "groupName": "contactinformation", "description": "Pediu para não ser contatado (registrado pelo B2B ON).",
                          "options": [{"label": "Sim", "value": "true"}, {"label": "Não", "value": "false"}]}),
        ]
        for objeto, definicao in definicoes:
            try:
                self._escrever("POST", f"/crm/v3/properties/{objeto}", definicao)
            except ErroConector as erro:
                if erro.status != 409:
                    raise
        return CAMPOS_PADRAO


_ID_HUBSPOT = re.compile(r"^\d{1,20}$")


def _id_seguro(valor: str) -> str:
    """Id externo vai para o caminho da URL: só dígitos (anti path-injection)."""
    if not _ID_HUBSPOT.match(str(valor)):
        raise ValueError("Id HubSpot inválido.")
    return str(valor)


def fabrica(db, conexao) -> HubSpotAdapter:
    return HubSpotAdapter(conexao.tenant_id, json.loads(conexao.credenciais or "{}"), conexao.configuracao or {},
                          ao_renovar_token=persistidor(db, conexao))
