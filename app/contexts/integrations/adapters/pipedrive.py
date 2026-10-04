"""Conector Pipedrive ↔ modelo canônico (Fase 13, conector 3 de 4; escrita D-087).

Leitura via API v1 (`https://api.pipedrive.com/v1`, host fixo).
Autenticação por API token no header `x-api-token` (nunca na URL, que
acaba em log) ou, desde D-087, pelo app OAuth da B2B ON: Bearer no
`api_domain` da empresa (`https://<empresa>.pipedrive.com`, validado) e
renovação em `oauth.pipedrive.com`.

Escrita (D-087): organização procurada pelo CNPJ (campo personalizado) ou
nome exato, pessoa pelo e-mail — encontradas, não são alteradas; negócio,
atividades (concluídas), notas e tarefas (atividade "task" em aberto)
criados; sinais do MAP e opt-out em campos PRÓPRIOS (`preparar_campos` cria
e devolve as chaves). Sem campo de opt-out configurado, usa o
`marketing_status` (exige o Pipedrive Campaigns). Paginação `start`/`limit` (`additional_data.pagination`);
incremental por `/recents?since_timestamp=`. BETA (D-041). Mapeamento em
`docs/b2bon/14_INTEGRATION_HUB.md` §Pipedrive.

Pipedrive não tem ciclo de vida de conta nem estágio de ganho/perda:
cliente = organização com negócio ganho (`won_deals_count`); ganho/perda
vem do `status` do negócio, e todo estágio é aberto.

Configuração: `campo_cnpj` (chave do campo personalizado da organização,
o hash de 40 caracteres que a API usa).
"""

import html
import json
import re
from datetime import UTC, datetime
from decimal import Decimal

import httpx

from app.contexts.integrations.adapters import interacoes
from app.contexts.integrations.adapters.http_base import AcessoBearer, ClienteHttp, host_permitido, persistidor
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

SYSTEM = "pipedrive"
API = "https://api.pipedrive.com"
OAUTH = "https://oauth.pipedrive.com"
HOSTS_EMPRESA = (".pipedrive.com",)
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


_TIPO_SAIDA = {TipoAtividadeSaida.EMAIL: "email", TipoAtividadeSaida.LIGACAO: "call", TipoAtividadeSaida.REUNIAO: "meeting",
               TipoAtividadeSaida.WHATSAPP: "task", TipoAtividadeSaida.LINKEDIN: "task"}
_ID_NUM = re.compile(r"^\d{1,20}$")


def _num(valor) -> int:
    if not _ID_NUM.match(str(valor)):
        raise ValueError("Id Pipedrive inválido.")
    return int(valor)


def validar(credenciais: dict, configuracao: dict) -> None:
    if credenciais.get("oauth_app") == "b2bon":
        dominio = credenciais.get("api_domain")
        if not isinstance(dominio, str) or not host_permitido(dominio, HOSTS_EMPRESA):
            raise ValueError("api_domain deve ser https://<empresa>.pipedrive.com")
        if not credenciais.get("access_token"):
            raise ValueError("Conexão OAuth sem access_token.")
        extras = set(credenciais) - {"oauth_app", "access_token", "refresh_token", "api_domain"}
    else:
        token = credenciais.get("api_token")
        if not isinstance(token, str) or not _TOKEN.match(token):
            raise ValueError("Informe o api_token do Pipedrive (Configurações pessoais → API).")
        extras = set(credenciais) - {"api_token"}
    if extras:
        raise ValueError(f"Credenciais não reconhecidas: {sorted(extras)}")
    campo = configuracao.get("campo_cnpj")
    if campo is not None and not (isinstance(campo, str) and _CAMPO.match(campo)):
        raise ValueError("campo_cnpj deve ser a chave do campo personalizado da organização.")
    nps = configuracao.get("campo_nps")
    if nps is not None and not (isinstance(nps, str) and _CAMPO.match(nps)):
        raise ValueError("campo_nps deve ser o nome/id do campo com a nota NPS (0–10) da empresa.")


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


class PipedriveAdapter(AcessoBearer, CrmAdapter):
    SISTEMA = SYSTEM

    def __init__(self, tenant_id: str, credenciais: dict, configuracao: dict | None = None,
                 transport: httpx.BaseTransport | None = None, ao_renovar_token=None) -> None:
        configuracao = configuracao or {}
        validar(credenciais, configuracao)
        self._tenant_id = tenant_id
        self._campo_cnpj = configuracao.get("campo_cnpj")
        self._campo_nps = configuracao.get("campo_nps")
        self._interacoes: dict[str, list[Interaction]] | None = None
        self._iniciar_acesso(credenciais, transport, ao_renovar_token)

    # --- HTTP + auth: API token (header) ou OAuth (Bearer no domínio da empresa) ---
    def _oauth(self) -> bool:
        return self._credenciais.get("oauth_app") == "b2bon"

    def _base_url(self) -> str:
        return self._credenciais["api_domain"].rstrip("/") if self._oauth() else API

    def _novo_cliente(self) -> ClienteHttp:
        if self._oauth():
            return super()._novo_cliente()
        return ClienteHttp(SYSTEM, API, {"x-api-token": self._credenciais["api_token"], "Accept": "application/json"}, self._transport)

    def _pode_renovar(self) -> bool:
        return self._oauth() and bool(self._credenciais.get("refresh_token") and settings.oauth_pipedrive_client_id)

    def _renovar_token(self) -> dict:
        resposta = self._cliente_auth(OAUTH).post_form(
            "/oauth/token", {"grant_type": "refresh_token", "refresh_token": self._credenciais["refresh_token"]},
            auth=(settings.oauth_pipedrive_client_id, settings.oauth_pipedrive_client_secret),
        )
        mudancas = {"access_token": resposta.get("access_token"), "refresh_token": resposta.get("refresh_token") or self._credenciais["refresh_token"]}
        if resposta.get("api_domain") and host_permitido(resposta["api_domain"], HOSTS_EMPRESA):
            mudancas["api_domain"] = resposta["api_domain"]
        return mudancas

    def _meu(self, tenant_id: str) -> bool:
        return tenant_id == self._tenant_id

    @staticmethod
    def _inicio(cursor: str | None) -> int:
        if cursor is not None and not cursor.isdigit():
            raise ValueError("Cursor Pipedrive inválido.")
        return int(cursor or 0)

    def _listar(self, caminho: str, cursor: str | None, **params) -> tuple[list[dict], str | None]:
        resposta = self._get(f"/v1/{caminho}", {"start": self._inicio(cursor), "limit": _LIMITE, **params})
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
        return AdapterCapabilities(system=SYSTEM, readable_entities=_LEGIVEIS, writable_entities=ESCRITAS, incremental_sync=True, webhooks=True)

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
        """Pipedrive não tem NPS nativo: lê o campo personalizado `campo_nps` (D-087)."""
        if not self._campo_nps:
            return Page(items=[])
        return self._pagina(tenant_id, "organization", cursor, None, self._metrica_nps)

    def _metrica_nps(self, r: dict, agora: datetime) -> CSMetric | None:
        nota = interacoes.nota_nps(r.get(self._campo_nps))
        if nota is None:
            return None
        return CSMetric(id=cid("cs_metric", f"nps-{r['id']}"), tenant_id=self._tenant_id, source=_src("organization", r["id"], agora),
                        account_id=cid("account", r["id"]), metric="NPS", value=nota, scale_max=10, collected_at=_data(r.get("update_time")))

    def list_offers(self, tenant_id):
        if not self._meu(tenant_id):
            return []
        agora = datetime.now(UTC)
        return [
            Offer(id=cid("offer", r["id"]), tenant_id=self._tenant_id, source=_src("product", r["id"], agora), name=r.get("name") or f"Produto {r['id']}",
                  category=str(r["category"]) if r.get("category") else None, description=r.get("description"), active=bool(r.get("active_flag", True)))
            for r in self._todos("products")
        ]


    # --- Escrita (D-087) ----------------------------------------------------------
    def _exigir_meu(self, tenant_id: str) -> None:
        if not self._meu(tenant_id):
            raise PermissionError("Conexão de outro tenant.")

    def _criar(self, recurso: str, corpo: dict) -> str:
        resposta = self._escrever("POST", f"/v1/{recurso}", {k: v for k, v in corpo.items() if v not in (None, "")})
        return str((resposta.get("data") or {})["id"])

    def _buscar(self, recurso: str, termo: str, campo: str) -> str | None:
        resposta = self._get(f"/v1/{recurso}/search", {"term": termo, "fields": campo, "exact_match": "true", "limit": 1})
        itens = (resposta.get("data") or {}).get("items") or []
        return str(itens[0]["item"]["id"]) if itens else None

    def garantir_empresa(self, tenant_id: str, empresa: EmpresaSaida) -> str:
        self._exigir_meu(tenant_id)
        if empresa.cnpj and self._campo_cnpj:
            existente = self._buscar("organizations", empresa.cnpj, "custom_fields")
            if existente:
                return existente
        existente = self._buscar("organizations", empresa.nome, "name")
        if existente:
            return existente
        corpo = {"name": empresa.nome, "owner_id": _num(empresa.dono_externo_id) if empresa.dono_externo_id else None}
        if self._campo_cnpj and empresa.cnpj:
            corpo[self._campo_cnpj] = empresa.cnpj
        return self._criar("organizations", corpo)

    def garantir_pessoa(self, tenant_id: str, pessoa: PessoaSaida) -> str:
        self._exigir_meu(tenant_id)
        if pessoa.email:
            existente = self._buscar("persons", pessoa.email.lower(), "email")
            if existente:
                return existente
        return self._criar("persons", {
            "name": pessoa.nome, "email": [{"value": pessoa.email, "primary": True}] if pessoa.email else None,
            "phone": [{"value": pessoa.telefone, "primary": True}] if pessoa.telefone else None, "job_title": pessoa.cargo,
            "org_id": _num(pessoa.empresa_id) if pessoa.empresa_id else None,
            "owner_id": _num(pessoa.dono_externo_id) if pessoa.dono_externo_id else None,
        })

    def _vinculos(self, empresa_id, pessoa_id, negocio_id) -> dict:
        return {"org_id": _num(empresa_id) if empresa_id else None, "person_id": _num(pessoa_id) if pessoa_id else None,
                "deal_id": _num(negocio_id) if negocio_id else None}

    def registrar_atividade(self, tenant_id: str, atividade: AtividadeSaida) -> str:
        self._exigir_meu(tenant_id)
        vinculos = self._vinculos(atividade.empresa_id, atividade.pessoa_id, atividade.negocio_id)
        if atividade.tipo == TipoAtividadeSaida.NOTA:
            conteudo = f"<b>{html.escape(atividade.assunto)}</b><br>{html.escape(atividade.descricao)}".replace("\n", "<br>")
            return self._criar("notes", {"content": conteudo, **vinculos})
        quando = atividade.ocorrida_em.astimezone(UTC)
        canal = {TipoAtividadeSaida.WHATSAPP: "[WhatsApp] ", TipoAtividadeSaida.LINKEDIN: "[LinkedIn] "}.get(atividade.tipo, "")
        reuniao = atividade.tipo == TipoAtividadeSaida.REUNIAO
        return self._criar("activities", {
            "subject": f"{canal}{atividade.assunto}"[:255], "type": _TIPO_SAIDA.get(atividade.tipo, "task"),
            "done": 0 if reuniao and quando > datetime.now(UTC) else 1,
            "due_date": quando.strftime("%Y-%m-%d"), "due_time": quando.strftime("%H:%M"),
            "duration": f"{(atividade.duracao_minutos or 30) // 60:02d}:{(atividade.duracao_minutos or 30) % 60:02d}" if reuniao else None,
            "note": atividade.descricao, "user_id": _num(atividade.dono_externo_id) if atividade.dono_externo_id else None, **vinculos,
        })

    def criar_negocio(self, tenant_id: str, negocio: NegocioSaida) -> str:
        self._exigir_meu(tenant_id)
        return self._criar("deals", {
            "title": negocio.nome, "org_id": _num(negocio.empresa_id), "person_id": _num(negocio.pessoa_id) if negocio.pessoa_id else None,
            "stage_id": _num(negocio.estagio_id), "user_id": _num(negocio.dono_externo_id) if negocio.dono_externo_id else None,
            "expected_close_date": negocio.previsao_fechamento.isoformat() if negocio.previsao_fechamento else None,
        })

    def criar_tarefa(self, tenant_id: str, tarefa: TarefaSaida) -> str:
        self._exigir_meu(tenant_id)
        return self._criar("activities", {
            "subject": tarefa.assunto[:255], "type": "task", "done": 0, "due_date": tarefa.vencimento.isoformat(), "note": tarefa.descricao,
            "org_id": _num(tarefa.empresa_id) if tarefa.empresa_id else None,
            "user_id": _num(tarefa.dono_externo_id) if tarefa.dono_externo_id else None,
        })

    def marcar_optout(self, tenant_id: str, pessoa_id: str, campos: CamposProprios) -> None:
        self._exigir_meu(tenant_id)
        corpo = {campos.optout: "sim"} if campos.optout else {"marketing_status": "unsubscribed"}
        self._escrever("PUT", f"/v1/persons/{_num(pessoa_id)}", corpo)

    def gravar_sinais_conta(self, tenant_id: str, sinais: SinaisContaSaida, campos: CamposProprios) -> None:
        self._exigir_meu(tenant_id)
        corpo = {}
        if campos.score_risco:
            corpo[campos.score_risco] = round(sinais.score_risco, 1)
        if campos.nivel_risco:
            corpo[campos.nivel_risco] = sinais.nivel_risco
        if not corpo:
            raise OperacaoNaoSuportada("Nenhum campo de risco configurado.")
        self._escrever("PUT", f"/v1/organizations/{_num(sinais.empresa_id)}", corpo)

    def preparar_campos(self, tenant_id: str) -> CamposProprios:
        """Cria os campos personalizados da B2B ON (ou reaproveita os já
        criados, pelo nome) e devolve as chaves (hash) que a API usa."""
        self._exigir_meu(tenant_id)
        chaves = {}
        for nome_campo, recurso, rotulo, tipo in (
            ("score_risco", "organizationFields", "B2B ON — score de risco", "double"),
            ("nivel_risco", "organizationFields", "B2B ON — nível de risco", "varchar"),
            ("optout", "personFields", "B2B ON — opt-out", "varchar"),
        ):
            existentes = {c.get("name"): c.get("key") for c in self._todos(recurso)}
            chaves[nome_campo] = existentes.get(rotulo) or (self._escrever("POST", f"/v1/{recurso}", {"name": rotulo, "field_type": tipo}).get("data") or {})["key"]
        return CamposProprios(**chaves)


def fabrica(db, conexao) -> PipedriveAdapter:
    return PipedriveAdapter(conexao.tenant_id, json.loads(conexao.credenciais or "{}"), conexao.configuracao or {},
                            ao_renovar_token=persistidor(db, conexao))
