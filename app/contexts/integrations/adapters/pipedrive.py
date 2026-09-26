"""Conector Pipedrive → modelo canônico (Fase 13, conector 3 de 4).

Somente leitura, via API v1 (`https://api.pipedrive.com/v1`, host fixo).
Autenticação por API token no header `x-api-token` (nunca na URL, que
acaba em log). Paginação `start`/`limit` (`additional_data.pagination`);
incremental por `/recents?since_timestamp=`. BETA (D-041). Mapeamento em
`docs/b2bon/14_INTEGRATION_HUB.md` §Pipedrive.

Pipedrive não tem ciclo de vida de conta nem estágio de ganho/perda:
cliente = organização com negócio ganho (`won_deals_count`); ganho/perda
vem do `status` do negócio, e todo estágio é aberto.

Configuração: `campo_cnpj` (chave do campo personalizado da organização,
o hash de 40 caracteres que a API usa).
"""

import json
import re
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from app.contexts.integrations.adapters import interacoes
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

SYSTEM = "pipedrive"
API = "https://api.pipedrive.com"
_TOKEN = re.compile(r"^[A-Za-z0-9]{20,100}$")
_CAMPO = re.compile(r"^[a-z0-9_]{1,64}$")
_LIMITE = 100

_LEGIVEIS = frozenset({
    "organizations", "accounts", "customers", "people", "contacts", "pipelines", "stages",
    "opportunities", "activities", "interactions", "offers",
})
_TIPO_ATIVIDADE = {"call": ActivityKind.CALL, "email": ActivityKind.EMAIL, "meeting": ActivityKind.MEETING,
                   "task": ActivityKind.TASK, "deadline": ActivityKind.TASK}
_STATUS = {"won": OpportunityStatus.WON, "lost": OpportunityStatus.LOST, "open": OpportunityStatus.OPEN}
# objeto de /recents → endpoint de listagem
_RECENTES = {"organization": "organizations", "person": "persons", "deal": "deals"}


def validar(credenciais: dict, configuracao: dict) -> None:
    token = credenciais.get("api_token")
    if not isinstance(token, str) or not _TOKEN.match(token):
        raise ValueError("Informe o api_token do Pipedrive (Configurações pessoais → API).")
    extras = set(credenciais) - {"api_token"}
    if extras:
        raise ValueError(f"Credenciais não reconhecidas: {sorted(extras)}")
    campo = configuracao.get("campo_cnpj")
    if campo is not None and not (isinstance(campo, str) and _CAMPO.match(campo)):
        raise ValueError("campo_cnpj deve ser a chave do campo personalizado da organização.")


def cid(entidade: str, id_) -> str:
    return canonical_id(SYSTEM, entidade, id_)


def _src(entidade: str, id_, agora: datetime) -> SourceRef:
    return SourceRef(system=SYSTEM, external_id=str(id_), entity=entidade, fetched_at=agora)


def _data(valor: str | None) -> datetime | None:
    """Pipedrive devolve 'AAAA-MM-DD HH:MM:SS' em UTC, ou só a data."""
    if not valor:
        return None
    return datetime.fromisoformat(valor.replace(" ", "T")).replace(tzinfo=UTC)


def _ref(valor) -> str | None:
    """Referência que pode vir como número ou objeto (`{"value": 5}` / `{"id": 5}`)."""
    if isinstance(valor, dict):
        valor = valor.get("value", valor.get("id"))
    return str(valor) if valor not in (None, "", 0) else None


def _principal(valores) -> str | None:
    if not isinstance(valores, list) or not valores:
        return None
    escolhido = next((v for v in valores if v.get("primary")), valores[0])
    return escolhido.get("value") or None


class PipedriveAdapter(CrmAdapter):
    def __init__(self, tenant_id: str, credenciais: dict, configuracao: dict | None = None,
                 transport: httpx.BaseTransport | None = None) -> None:
        configuracao = configuracao or {}
        validar(credenciais, configuracao)
        self._tenant_id = tenant_id
        self._campo_cnpj = configuracao.get("campo_cnpj")
        self._interacoes: dict[str, list[Interaction]] | None = None
        self._http = ClienteHttp(SYSTEM, API, {"x-api-token": credenciais["api_token"], "Accept": "application/json"}, transport)

    def _meu(self, tenant_id: str) -> bool:
        return tenant_id == self._tenant_id

    @staticmethod
    def _inicio(cursor: str | None) -> int:
        if cursor is not None and not cursor.isdigit():
            raise ValueError("Cursor Pipedrive inválido.")
        return int(cursor or 0)

    def _listar(self, caminho: str, cursor: str | None, **params) -> tuple[list[dict], str | None]:
        resposta = self._http.get(f"/v1/{caminho}", {"start": self._inicio(cursor), "limit": _LIMITE, **params})
        paginacao = (resposta.get("additional_data") or {}).get("pagination") or {}
        proximo = str(paginacao["next_start"]) if paginacao.get("more_items_in_collection") else None
        return resposta.get("data") or [], proximo

    def _todos(self, caminho: str, **params) -> list[dict]:
        registros, cursor = self._listar(caminho, None, **params)
        while cursor:
            mais, cursor = self._listar(caminho, cursor, **params)
            registros.extend(mais)
        return registros

    def _registros(self, objeto: str, cursor: str | None, updated_since: datetime | None) -> tuple[list[dict], str | None]:
        if updated_since is None:
            return self._listar(_RECENTES[objeto], cursor)
        if updated_since.tzinfo is not None:
            updated_since = updated_since.astimezone(UTC)
        itens, proximo = self._listar("recents", cursor, items=objeto, since_timestamp=updated_since.strftime("%Y-%m-%d %H:%M:%S"))
        return [i["data"] for i in itens if i.get("item") == objeto and i.get("data")], proximo

    def _pagina(self, tenant_id: str, objeto: str, cursor, updated_since, converter) -> Page:
        if not self._meu(tenant_id):
            return Page(items=[])
        agora = datetime.now(UTC)
        registros, proximo = self._registros(objeto, cursor, updated_since)
        return Page(items=[i for i in (converter(r, agora) for r in registros) if i is not None], next_cursor=proximo)

    # --- Contrato ----------------------------------------------------------------
    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(system=SYSTEM, readable_entities=_LEGIVEIS, incremental_sync=True)

    def _organizacao(self, r: dict, agora: datetime) -> Organization:
        cnpj = re.sub(r"\D", "", str(r.get(self._campo_cnpj) or "")) if self._campo_cnpj else ""
        return Organization(
            id=cid("organization", r["id"]), tenant_id=self._tenant_id, source=_src("organization", r["id"], agora),
            legal_name=r.get("name") or f"Organização {r['id']}", tax_id=cnpj or None,
            region=r.get("address_admin_area_level_1") or None,
            created_at=_data(r.get("add_time")), updated_at=_data(r.get("update_time")),
        )

    def _conta(self, r: dict, agora: datetime) -> Account:
        return Account(
            id=cid("account", r["id"]), tenant_id=self._tenant_id, source=_src("organization", r["id"], agora),
            organization_id=cid("organization", r["id"]), owner_user_id=_ref(r.get("owner_id")),
            lifecycle=AccountLifecycle.CUSTOMER if (r.get("won_deals_count") or 0) > 0 else AccountLifecycle.PROSPECT,
            created_at=_data(r.get("add_time")), updated_at=_data(r.get("update_time")),
        )

    def list_organizations(self, tenant_id, cursor=None, updated_since=None, limit=100):
        return self._pagina(tenant_id, "organization", cursor, updated_since, self._organizacao)

    def list_accounts(self, tenant_id, cursor=None, updated_since=None, limit=100):
        return self._pagina(tenant_id, "organization", cursor, updated_since, self._conta)

    def list_customers(self, tenant_id, cursor=None, limit=100):
        """Cliente desde o primeiro negócio ganho (`won_time`); churn desconhecido."""
        if not self._meu(tenant_id):
            return Page(items=[])
        agora = datetime.now(UTC)
        primeira: dict[str, datetime] = {}
        for negocio in self._todos("deals", status="won"):
            org, ganho = _ref(negocio.get("org_id")), _data(negocio.get("won_time"))
            if org and ganho and (org not in primeira or ganho < primeira[org]):
                primeira[org] = ganho
        return Page(items=[
            Customer(id=cid("customer", org), tenant_id=self._tenant_id, source=_src("organization", org, agora),
                     account_id=cid("account", org), customer_since=desde)
            for org, desde in primeira.items()
        ])

    def _pessoa(self, r: dict, agora: datetime) -> Person:
        org = _ref(r.get("org_id"))
        return Person(
            id=cid("person", r["id"]), tenant_id=self._tenant_id, source=_src("person", r["id"], agora),
            organization_id=cid("organization", org) if org else None, full_name=r.get("name") or "(sem nome)",
            job_title=r.get("job_title") or None, email=_principal(r.get("email")), phone=_principal(r.get("phone")),
            # descadastro de marketing sem data própria: última alteração é o limite conhecido
            suppressed_at=(_data(r.get("update_time")) or agora) if r.get("marketing_status") == "unsubscribed" else None,
            created_at=_data(r.get("add_time")), updated_at=_data(r.get("update_time")),
        )

    def _contato(self, r: dict, agora: datetime) -> Contact | None:
        org = _ref(r.get("org_id"))
        if not org:
            return None
        return Contact(id=cid("contact", r["id"]), tenant_id=self._tenant_id, source=_src("person", r["id"], agora),
                       account_id=cid("account", org), person_id=cid("person", r["id"]))

    def list_people(self, tenant_id, cursor=None, updated_since=None, limit=100):
        return self._pagina(tenant_id, "person", cursor, updated_since, self._pessoa)

    def list_contacts(self, tenant_id, cursor=None, limit=100):
        return self._pagina(tenant_id, "person", cursor, None, self._contato)

    def list_pipelines(self, tenant_id):
        if not self._meu(tenant_id):
            return []
        agora = datetime.now(UTC)
        return [Pipeline(id=cid("pipeline", p["id"]), tenant_id=self._tenant_id, source=_src("pipeline", p["id"], agora), name=p["name"])
                for p in self._todos("pipelines")]

    def list_stages(self, tenant_id):
        if not self._meu(tenant_id):
            return []
        agora = datetime.now(UTC)
        return [
            PipelineStage(id=cid("stage", e["id"]), tenant_id=self._tenant_id, source=_src("stage", e["id"], agora),
                          pipeline_id=cid("pipeline", e["pipeline_id"]), name=e["name"], order=e.get("order_nr") or 0,
                          stage_type=StageType.OPEN)  # ganho/perda é status do negócio, não estágio
            for e in self._todos("stages")
        ]

    def _oportunidade(self, r: dict, agora: datetime) -> Opportunity | None:
        org = _ref(r.get("org_id"))
        status = _STATUS.get(r.get("status") or "")
        if not org or status is None:
            return None  # sem organização, ou excluído
        valor = r.get("value")
        fechado = status != OpportunityStatus.OPEN
        return Opportunity(
            id=cid("opportunity", r["id"]), tenant_id=self._tenant_id, source=_src("deal", r["id"], agora),
            account_id=cid("account", org), primary_contact_id=None, owner_user_id=_ref(r.get("user_id")),
            pipeline_id=cid("pipeline", r["pipeline_id"]), stage_id=cid("stage", r["stage_id"]),
            name=r.get("title") or f"Negócio {r['id']}",
            amount=Money(amount=Decimal(str(valor)), currency=r.get("currency") or "BRL") if valor not in (None, "") else None,
            probability=r.get("probability"), status=status, lost_reason=r.get("lost_reason") or None,
            closed_at=(_data(r.get("won_time")) if status == OpportunityStatus.WON else _data(r.get("lost_time"))) if fechado else None,
            created_at=_data(r.get("add_time")), updated_at=_data(r.get("update_time")),
        )

    def list_opportunities(self, tenant_id, cursor=None, updated_since=None, limit=100):
        return self._pagina(tenant_id, "deal", cursor, updated_since, self._oportunidade)

    def _atividade(self, r: dict, agora: datetime) -> Activity:
        org, negocio = _ref(r.get("org_id")), _ref(r.get("deal_id"))
        tipo = r.get("type") or ""
        return Activity(
            id=cid("activity", r["id"]), tenant_id=self._tenant_id, source=_src("activity", r["id"], agora),
            account_id=cid("account", org) if org else None, opportunity_id=cid("opportunity", negocio) if negocio else None,
            user_id=_ref(r.get("user_id")), kind=_TIPO_ATIVIDADE.get(tipo, ActivityKind.OTHER), source_type=tipo or "activity",
            description=r.get("subject") or "", created_at=_data(r.get("marked_as_done_time")) or _data(r.get("add_time")),
        )

    def list_activities(self, tenant_id, cursor=None, limit=100):
        if not self._meu(tenant_id):
            return Page(items=[])
        agora = datetime.now(UTC)
        registros, proximo = self._listar("activities", cursor, user_id=0)  # user_id=0: de todos os usuários
        return Page(items=[self._atividade(r, agora) for r in registros], next_cursor=proximo)

    def list_interactions(self, tenant_id, account_id=None, cursor=None, limit=100):
        """Atividades concluídas com organização = contato registrado. Lidas
        uma vez por instância: o MAP pergunta conta a conta."""
        if not self._meu(tenant_id):
            return Page(items=[])
        if self._interacoes is None:
            agora = datetime.now(UTC)
            self._interacoes = interacoes.por_conta(self._todos("activities", user_id=0, done=1), lambda r: self._atividade(r, agora), cid, self._tenant_id)
        return interacoes.pagina(self._interacoes, account_id)

    def list_cs_metrics(self, tenant_id, cursor=None, limit=100):
        return Page(items=[])  # Pipedrive não tem NPS

    def list_offers(self, tenant_id):
        if not self._meu(tenant_id):
            return []
        agora = datetime.now(UTC)
        return [
            Offer(id=cid("offer", r["id"]), tenant_id=self._tenant_id, source=_src("product", r["id"], agora), name=r.get("name") or f"Produto {r['id']}",
                  category=str(r["category"]) if r.get("category") else None, description=r.get("description"), active=bool(r.get("active_flag", True)))
            for r in self._todos("products")
        ]


def fabrica(db, conexao) -> PipedriveAdapter:
    return PipedriveAdapter(conexao.tenant_id, json.loads(conexao.credenciais or "{}"), conexao.configuracao or {})
