"""Conector RD Station CRM → modelo canônico (Fase 13, conector 4 de 4).

Somente leitura, via API v1 (`https://crm.rdstation.com/api/v1`, host
fixo). A v1 só aceita o token na query string (`?token=`): o filtro de
log do `http_base` mascara o valor e o erro do sync também é mascarado.
Paginação por `page`/`limit` + `has_more`. A v1 não filtra por data de
alteração: **sem sync incremental** (capacidade declarada como falsa; o
sync lê tudo). BETA (D-041). Mapeamento em
`docs/b2bon/14_INTEGRATION_HUB.md` §RD Station CRM.

Sem ciclo de vida no RD Station CRM: cliente = organização com negócio
ganho (`win: true`), desde o primeiro `closed_at` ganho; todo estágio é
aberto (ganho/perda é o `win` do negócio).

Configuração: `moeda` (padrão BRL; a v1 não informa moeda) e
`campo_cnpj` (`custom_field_id` do campo personalizado da organização).
"""

import json
import re
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from app.contexts.integrations.adapters.http_base import ClienteHttp
from app.contexts.integrations.contract import AdapterCapabilities, CrmAdapter, Page
from app.contexts.shared.canonical.base import SourceRef, canonical_id
from app.contexts.shared.canonical.commercial import (
    Account,
    AccountLifecycle,
    Activity,
    ActivityKind,
    Contact,
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

SYSTEM = "rd_station"
API = "https://crm.rdstation.com"
_TOKEN = re.compile(r"^[A-Za-z0-9_\-]{16,100}$")
_ID = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
_MOEDA = re.compile(r"^[A-Z]{3}$")
_LIMITE = 200

_LEGIVEIS = frozenset({
    "organizations", "accounts", "customers", "people", "contacts", "pipelines", "stages",
    "opportunities", "activities", "interactions", "offers",
})
_TIPO_TAREFA = {"call": ActivityKind.CALL, "email": ActivityKind.EMAIL, "meeting": ActivityKind.MEETING,
                "visit": ActivityKind.MEETING, "task": ActivityKind.TASK}


def validar(credenciais: dict, configuracao: dict) -> None:
    token = credenciais.get("token")
    if not isinstance(token, str) or not _TOKEN.match(token):
        raise ValueError("Informe o token da API do RD Station CRM (Perfil → Token da instância).")
    extras = set(credenciais) - {"token"}
    if extras:
        raise ValueError(f"Credenciais não reconhecidas: {sorted(extras)}")
    campo = configuracao.get("campo_cnpj")
    if campo is not None and not (isinstance(campo, str) and _ID.match(campo)):
        raise ValueError("campo_cnpj deve ser o id do campo personalizado da organização.")
    moeda = configuracao.get("moeda", "BRL")
    if not (isinstance(moeda, str) and _MOEDA.match(moeda)):
        raise ValueError("moeda deve ser um código ISO 4217 (ex.: BRL).")


def cid(entidade: str, id_) -> str:
    return canonical_id(SYSTEM, entidade, id_)


def _src(entidade: str, id_, agora: datetime) -> SourceRef:
    return SourceRef(system=SYSTEM, external_id=str(id_), entity=entidade, fetched_at=agora)


def _data(valor: str | None) -> datetime | None:
    if not valor:
        return None
    momento = datetime.fromisoformat(valor.replace("Z", "+00:00"))
    return momento if momento.tzinfo else momento.replace(tzinfo=UTC)


def _id(valor) -> str | None:
    if isinstance(valor, dict):
        valor = valor.get("id") or valor.get("_id")
    return str(valor) if valor else None


def _primeiro(lista, chave: str) -> str | None:
    if not isinstance(lista, list):
        return None
    return next((item.get(chave) for item in lista if item.get(chave)), None)


class RdStationCrmAdapter(CrmAdapter):
    def __init__(self, tenant_id: str, credenciais: dict, configuracao: dict | None = None,
                 transport: httpx.BaseTransport | None = None) -> None:
        configuracao = configuracao or {}
        validar(credenciais, configuracao)
        self._tenant_id = tenant_id
        self._token = credenciais["token"]
        self._moeda = configuracao.get("moeda", "BRL")
        self._campo_cnpj = configuracao.get("campo_cnpj")
        self._negocios: list[dict] | None = None
        self._ganhos: dict[str, datetime] | None = None
        self._pipelines: list[dict] | None = None
        self._interacoes: dict[str, list[Interaction]] | None = None
        self._http = ClienteHttp(SYSTEM, API, {"Accept": "application/json"}, transport)

    def _meu(self, tenant_id: str) -> bool:
        return tenant_id == self._tenant_id

    def _get(self, recurso: str, **params) -> dict | list:
        return self._http.get(f"/api/v1/{recurso}", {"token": self._token, **params})

    def _listar(self, recurso: str, chave: str, cursor: str | None, **params) -> tuple[list[dict], str | None]:
        if cursor is not None and not cursor.isdigit():
            raise ValueError("Cursor RD Station inválido.")
        pagina = int(cursor or 1)
        resposta = self._get(recurso, page=pagina, limit=_LIMITE, **params)
        return resposta.get(chave) or [], str(pagina + 1) if resposta.get("has_more") else None

    def _todos(self, recurso: str, chave: str, **params) -> list[dict]:
        registros, cursor = self._listar(recurso, chave, None, **params)
        while cursor:
            mais, cursor = self._listar(recurso, chave, cursor, **params)
            registros.extend(mais)
        return registros

    def _pagina(self, tenant_id: str, recurso: str, chave: str, cursor, converter) -> Page:
        if not self._meu(tenant_id):
            return Page(items=[])
        agora = datetime.now(UTC)
        registros, proximo = self._listar(recurso, chave, cursor)
        return Page(items=[i for i in (converter(r, agora) for r in registros) if i is not None], next_cursor=proximo)

    def _todos_negocios(self) -> list[dict]:
        if self._negocios is None:
            self._negocios = self._todos("deals", "deals")
        return self._negocios

    def _todos_pipelines(self) -> list[dict]:
        if self._pipelines is None:
            resposta = self._get("deal_pipelines")
            self._pipelines = resposta if isinstance(resposta, list) else resposta.get("deal_pipelines", [])
        return self._pipelines

    # --- Contrato ----------------------------------------------------------------
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(system=SYSTEM, readable_entities=_LEGIVEIS, incremental_sync=False)

    def _cnpj(self, r: dict) -> str | None:
        if not self._campo_cnpj:
            return None
        valor = next((c.get("value") for c in r.get("custom_fields") or [] if c.get("custom_field_id") == self._campo_cnpj), None)
        return re.sub(r"\D", "", str(valor or "")) or None

    def _organizacao(self, r: dict, agora: datetime) -> Organization:
        site = r.get("url") or ""
        dominio = re.sub(r"^(https?://)?(www\.)?", "", site).split("/")[0] or None
        return Organization(
            id=cid("organization", r["id"]), tenant_id=self._tenant_id, source=_src("organization", r["id"], agora),
            legal_name=r.get("name") or f"Organização {r['id']}", tax_id=self._cnpj(r), domain=dominio,
            industry=_primeiro(r.get("organization_segments"), "name"),
            created_at=_data(r.get("created_at")), updated_at=_data(r.get("updated_at")),
        )

    def _ganhos_por_organizacao(self) -> dict[str, datetime]:
        if self._ganhos is not None:
            return self._ganhos
        primeira: dict[str, datetime] = {}
        for negocio in self._todos_negocios():
            org, fechado = _id(negocio.get("organization")), _data(negocio.get("closed_at"))
            if negocio.get("win") is True and org and fechado and (org not in primeira or fechado < primeira[org]):
                primeira[org] = fechado
        self._ganhos = primeira
        return primeira

    def _conta(self, r: dict, agora: datetime) -> Account:
        cliente = str(r["id"]) in self._ganhos_por_organizacao()
        return Account(
            id=cid("account", r["id"]), tenant_id=self._tenant_id, source=_src("organization", r["id"], agora),
            organization_id=cid("organization", r["id"]), owner_user_id=_id(r.get("user")),
            lifecycle=AccountLifecycle.CUSTOMER if cliente else AccountLifecycle.PROSPECT,
            created_at=_data(r.get("created_at")), updated_at=_data(r.get("updated_at")),
        )

    def list_organizations(self, tenant_id, cursor=None, updated_since=None, limit=100):
        return self._pagina(tenant_id, "organizations", "organizations", cursor, self._organizacao)

    def list_accounts(self, tenant_id, cursor=None, updated_since=None, limit=100):
        return self._pagina(tenant_id, "organizations", "organizations", cursor, self._conta)

    def list_customers(self, tenant_id, cursor=None, limit=100):
        if not self._meu(tenant_id):
            return Page(items=[])
        agora = datetime.now(UTC)
        return Page(items=[
            Customer(id=cid("customer", org), tenant_id=self._tenant_id, source=_src("organization", org, agora),
                     account_id=cid("account", org), customer_since=desde)
            for org, desde in self._ganhos_por_organizacao().items()
        ])

    def _pessoa(self, r: dict, agora: datetime) -> Person:
        org = _id(r.get("organization_id") or r.get("organization"))
        return Person(
            id=cid("person", r["id"]), tenant_id=self._tenant_id, source=_src("contact", r["id"], agora),
            organization_id=cid("organization", org) if org else None, full_name=r.get("name") or "(sem nome)",
            job_title=r.get("title") or None, email=_primeiro(r.get("emails"), "email"), phone=_primeiro(r.get("phones"), "phone"),
            created_at=_data(r.get("created_at")), updated_at=_data(r.get("updated_at")),
        )  # opt-out é do RD Station Marketing, não do CRM: suppressed_at desconhecido

    def _contato(self, r: dict, agora: datetime) -> Contact | None:
        org = _id(r.get("organization_id") or r.get("organization"))
        if not org:
            return None
        return Contact(id=cid("contact", r["id"]), tenant_id=self._tenant_id, source=_src("contact", r["id"], agora),
                       account_id=cid("account", org), person_id=cid("person", r["id"]))

    def list_people(self, tenant_id, cursor=None, updated_since=None, limit=100):
        return self._pagina(tenant_id, "contacts", "contacts", cursor, self._pessoa)

    def list_contacts(self, tenant_id, cursor=None, limit=100):
        return self._pagina(tenant_id, "contacts", "contacts", cursor, self._contato)

    def list_pipelines(self, tenant_id):
        if not self._meu(tenant_id):
            return []
        agora = datetime.now(UTC)
        return [Pipeline(id=cid("pipeline", p["id"]), tenant_id=self._tenant_id, source=_src("deal_pipeline", p["id"], agora), name=p["name"])
                for p in self._todos_pipelines()]

    def list_stages(self, tenant_id):
        if not self._meu(tenant_id):
            return []
        agora = datetime.now(UTC)
        return [
            PipelineStage(id=cid("stage", e["id"]), tenant_id=self._tenant_id, source=_src("deal_stage", e["id"], agora),
                          pipeline_id=cid("pipeline", p["id"]), name=e["name"], order=e.get("order") or ordem,
                          stage_type=StageType.OPEN)  # ganho/perda é o `win` do negócio
            for p in self._todos_pipelines() for ordem, e in enumerate(p.get("deal_stages", []))
        ]

    def _oportunidade(self, r: dict, agora: datetime) -> Opportunity | None:
        org = _id(r.get("organization"))
        estagio = _id(r.get("deal_stage"))
        pipeline = next((p["id"] for p in self._todos_pipelines() for e in p.get("deal_stages", []) if str(e["id"]) == estagio), None)
        if not org or not estagio or pipeline is None:
            return None  # sem organização (não há conta) ou estágio fora dos funis
        win = r.get("win")
        status = OpportunityStatus.WON if win is True else OpportunityStatus.LOST if win is False else OpportunityStatus.OPEN
        valor = r.get("amount_total")
        return Opportunity(
            id=cid("opportunity", r["id"]), tenant_id=self._tenant_id, source=_src("deal", r["id"], agora),
            account_id=cid("account", org), owner_user_id=_id(r.get("user")), pipeline_id=cid("pipeline", pipeline),
            stage_id=cid("stage", estagio), name=r.get("name") or f"Negociação {r['id']}",
            amount=Money(amount=Decimal(str(valor)), currency=self._moeda) if valor is not None else None,
            status=status, lost_reason=(r.get("deal_lost_reason") or {}).get("name"),
            closed_at=_data(r.get("closed_at")) if status != OpportunityStatus.OPEN else None,
            created_at=_data(r.get("created_at")), updated_at=_data(r.get("updated_at")),
        )

    def list_opportunities(self, tenant_id, cursor=None, updated_since=None, limit=100):
        return self._pagina(tenant_id, "deals", "deals", cursor, self._oportunidade)

    def _organizacao_do_negocio(self, negocio_id: str | None) -> str | None:
        if not negocio_id:
            return None
        negocio = next((n for n in self._todos_negocios() if str(n["id"]) == negocio_id), None)
        return _id(negocio.get("organization")) if negocio else None

    def _atividade(self, r: dict, agora: datetime) -> Activity:
        negocio = _id(r.get("deal_id") or r.get("deal"))
        org = self._organizacao_do_negocio(negocio)
        tipo = r.get("type") or "task"
        return Activity(
            id=cid("task", r["id"]), tenant_id=self._tenant_id, source=_src("task", r["id"], agora),
            account_id=cid("account", org) if org else None, opportunity_id=cid("opportunity", negocio) if negocio else None,
            user_id=_id((r.get("users") or [None])[0]), kind=_TIPO_TAREFA.get(tipo, ActivityKind.OTHER), source_type=tipo,
            description=r.get("subject") or "", created_at=_data(r.get("done_date")) or _data(r.get("created_at")),
        )

    def list_activities(self, tenant_id, cursor=None, limit=100):
        if not self._meu(tenant_id):
            return Page(items=[])
        agora = datetime.now(UTC)
        registros, proximo = self._listar("tasks", "tasks", cursor)
        return Page(items=[self._atividade(r, agora) for r in registros], next_cursor=proximo)

    def list_interactions(self, tenant_id, account_id=None, cursor=None, limit=100):
        """Tarefas concluídas de negócios da organização = contato registrado.
        Lidas uma vez por instância (o MAP pergunta conta a conta)."""
        if not self._meu(tenant_id):
            return Page(items=[])
        if self._interacoes is None:
            agora = datetime.now(UTC)
            por_conta: dict[str, list[Interaction]] = {}
            for r in self._todos("tasks", "tasks", done="true"):
                atividade = self._atividade(r, agora)
                if atividade.account_id:
                    por_conta.setdefault(atividade.account_id, []).append(Interaction(
                        id=cid("interaction", r["id"]), tenant_id=self._tenant_id, source=atividade.source,
                        account_id=atividade.account_id, kind="contato", description=atividade.description or None,
                        created_at=atividade.created_at))
            self._interacoes = por_conta
        if account_id is not None:
            return Page(items=list(self._interacoes.get(account_id, [])))
        return Page(items=[i for itens in self._interacoes.values() for i in itens])

    def list_cs_metrics(self, tenant_id, cursor=None, limit=100):
        return Page(items=[])  # RD Station CRM não tem NPS

    def list_offers(self, tenant_id):
        if not self._meu(tenant_id):
            return []
        agora = datetime.now(UTC)
        return [
            Offer(id=cid("offer", r["id"]), tenant_id=self._tenant_id, source=_src("product", r["id"], agora),
                  name=r.get("name") or f"Produto {r['id']}", description=r.get("description"), active=r.get("visible", True) is not False)
            for r in self._todos("products", "products")
        ]


def fabrica(db, conexao) -> RdStationCrmAdapter:
    return RdStationCrmAdapter(conexao.tenant_id, json.loads(conexao.credenciais or "{}"), conexao.configuracao or {})
