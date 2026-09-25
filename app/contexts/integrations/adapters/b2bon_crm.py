"""Adapter do CRM da própria B2B ON → modelo canônico (Fase 2).

A B2B ON é "cliente zero" do próprio contrato (§11): o mesmo `CrmAdapter`
que os conectores externos implementarão na Fase 13. Somente leitura
nesta fase. Isolamento: toda query filtra `tenant_id` (testado em
`tests/unit/test_adapter_b2bon_crm.py`). Mapeamento campo a campo em
`docs/b2bon/ENTITY_MAPPING.md`.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.contexts.integrations.contract import AdapterCapabilities, CrmAdapter, Page
from app.contexts.shared.canonical.base import DataOrigin, SourceRef, canonical_id
from app.contexts.shared.canonical.commercial import (
    Account,
    AccountLifecycle,
    Activity,
    ActivityKind,
    BuyingRole,
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
from app.models.atividade import Atividade
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.estagio_funil import EstagioFunil
from app.models.interacao_conta import InteracaoConta
from app.models.negocio import Negocio
from app.models.oferta import Oferta
from app.models.pesquisa_nps import PesquisaNps

SYSTEM = "b2bon_crm"

_TIPO_ESTAGIO = {"aberto": StageType.OPEN, "ganho": StageType.WON, "perdido": StageType.LOST}
_STATUS_OPORTUNIDADE = {StageType.OPEN: OpportunityStatus.OPEN, StageType.WON: OpportunityStatus.WON, StageType.LOST: OpportunityStatus.LOST}
_TIPO_ATIVIDADE = {
    "ligacao": ActivityKind.CALL,
    "email": ActivityKind.EMAIL,
    "e-mail": ActivityKind.EMAIL,
    "reuniao": ActivityKind.MEETING,
    "nota": ActivityKind.NOTE,
    "tarefa": ActivityKind.TASK,
    "sistema": ActivityKind.STAGE_CHANGE,
}
_PAPEIS = {papel.value for papel in BuyingRole}


def cid(entidade: str, id_: int | str) -> str:
    return canonical_id(SYSTEM, entidade, id_)


def _src(entidade: str, id_: int | str) -> SourceRef:
    return SourceRef(system=SYSTEM, external_id=str(id_), entity=entidade)


def _money(valor: float | None) -> Money | None:
    return None if valor is None else Money(amount=Decimal(str(valor)))


def _lifecycle(conta: Conta) -> AccountLifecycle:
    if conta.cliente_cancelado_em is not None:
        return AccountLifecycle.CHURNED
    if conta.cliente_desde is not None:
        return AccountLifecycle.CUSTOMER
    if conta.status == "descartada":
        return AccountLifecycle.DISQUALIFIED
    if conta.status == "priorizada":
        return AccountLifecycle.QUALIFIED
    if conta.icp_id is None:
        return AccountLifecycle.LEAD
    return AccountLifecycle.PROSPECT


def _paginar(query, modelo, cursor: str | None, limit: int):
    if cursor:
        query = query.filter(modelo.id > int(cursor))
    linhas = query.order_by(modelo.id).limit(limit + 1).all()
    proximo = str(linhas[limit - 1].id) if len(linhas) > limit else None
    return linhas[:limit], proximo


class B2BOnCrmAdapter(CrmAdapter):
    def __init__(self, db: Session) -> None:
        self._db = db

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(
            system=SYSTEM,
            readable_entities=frozenset(
                {"Organization", "Account", "Customer", "Person", "Contact", "Pipeline", "PipelineStage",
                 "Opportunity", "Activity", "Interaction", "CSMetric", "Offer"}
            ),
            incremental_sync=True,
        )

    # --- Organization / Account / Customer (Conta) -----------------------------
    def _contas(self, tenant_id: str, cursor: str | None, updated_since: datetime | None, limit: int):
        query = self._db.query(Conta).filter(Conta.tenant_id == tenant_id)
        if updated_since is not None:
            query = query.filter(Conta.atualizado_em >= updated_since)
        return _paginar(query, Conta, cursor, limit)

    def _organization(self, conta: Conta) -> Organization:
        oficial = (conta.origem or "").startswith("receita")
        return Organization(
            id=cid("organization", conta.id),
            tenant_id=conta.tenant_id,
            source=_src("conta", conta.id),
            origin=DataOrigin.OFFICIAL if oficial else DataOrigin.INTERNAL,
            legal_name=conta.nome,
            trade_name=conta.nome_fantasia,
            tax_id=conta.cnpj,
            domain=conta.dominio,
            industry=conta.segmento,
            size=conta.porte,
            region=conta.regiao,
            created_at=conta.criado_em,
            updated_at=conta.atualizado_em,
        )

    def list_organizations(self, tenant_id, cursor=None, updated_since=None, limit=100) -> Page[Organization]:
        contas, proximo = self._contas(tenant_id, cursor, updated_since, limit)
        return Page[Organization](items=[self._organization(c) for c in contas], next_cursor=proximo)

    def list_accounts(self, tenant_id, cursor=None, updated_since=None, limit=100) -> Page[Account]:
        contas, proximo = self._contas(tenant_id, cursor, updated_since, limit)
        return Page[Account](
            items=[
                Account(
                    id=cid("account", c.id),
                    tenant_id=c.tenant_id,
                    source=_src("conta", c.id),
                    organization_id=cid("organization", c.id),
                    owner_user_id=cid("user", c.vendedor_usuario_id) if c.vendedor_usuario_id else None,
                    lifecycle=_lifecycle(c),
                    fit_score=c.score_aderencia,
                    next_step=c.proximo_passo,
                    next_step_at=c.proximo_passo_em,
                    created_at=c.criado_em,
                    updated_at=c.atualizado_em,
                )
                for c in contas
            ],
            next_cursor=proximo,
        )

    def list_customers(self, tenant_id, cursor=None, limit=100) -> Page[Customer]:
        query = self._db.query(Conta).filter(Conta.tenant_id == tenant_id, Conta.cliente_desde.isnot(None))
        contas, proximo = _paginar(query, Conta, cursor, limit)
        return Page[Customer](
            items=[
                Customer(
                    id=cid("customer", c.id),
                    tenant_id=c.tenant_id,
                    source=_src("conta", c.id),
                    account_id=cid("account", c.id),
                    customer_since=c.cliente_desde,
                    churned_at=c.cliente_cancelado_em,
                    created_at=c.criado_em,
                )
                for c in contas
            ],
            next_cursor=proximo,
        )

    # --- Person / Contact (Decisor) ----------------------------------------------
    def list_people(self, tenant_id, cursor=None, updated_since=None, limit=100) -> Page[Person]:
        query = self._db.query(Decisor).filter(Decisor.tenant_id == tenant_id)
        if updated_since is not None:
            query = query.filter(Decisor.criado_em >= updated_since)
        decisores, proximo = _paginar(query, Decisor, cursor, limit)
        return Page[Person](
            items=[
                Person(
                    id=cid("person", d.id),
                    tenant_id=d.tenant_id,
                    source=_src("decisor", d.id),
                    origin=DataOrigin.OFFICIAL if (d.origem or "").startswith("receita") else DataOrigin.INTERNAL,
                    organization_id=cid("organization", d.conta_id),
                    full_name=d.nome,
                    job_title=d.cargo,
                    email=d.email,
                    phone=d.telefone,
                    linkedin_url=d.linkedin_url,
                    suppressed_at=d.suprimido_em,
                    created_at=d.criado_em,
                )
                for d in decisores
            ],
            next_cursor=proximo,
        )

    def list_contacts(self, tenant_id, cursor=None, limit=100) -> Page[Contact]:
        query = self._db.query(Decisor).filter(Decisor.tenant_id == tenant_id)
        decisores, proximo = _paginar(query, Decisor, cursor, limit)
        return Page[Contact](
            items=[
                Contact(
                    id=cid("contact", d.id),
                    tenant_id=d.tenant_id,
                    source=_src("decisor", d.id),
                    account_id=cid("account", d.conta_id),
                    person_id=cid("person", d.id),
                    buying_role=BuyingRole(d.papel_confirmado) if d.papel_confirmado in _PAPEIS else BuyingRole.UNKNOWN,
                    buying_role_confirmed=d.papel_confirmado in _PAPEIS,
                    last_interaction_at=d.ultima_interacao_em,
                    created_at=d.criado_em,
                )
                for d in decisores
            ],
            next_cursor=proximo,
        )

    # --- Pipeline / Stage / Opportunity (Negocio) ---------------------------------
    def list_pipelines(self, tenant_id) -> list[Pipeline]:
        # O CRM da B2B ON tem um funil único por tenant.
        return [Pipeline(id=cid("pipeline", tenant_id), tenant_id=tenant_id, source=_src("funil", tenant_id), name="Funil")]

    def _estagios(self, tenant_id: str) -> list[EstagioFunil]:
        return self._db.query(EstagioFunil).filter(EstagioFunil.tenant_id == tenant_id).order_by(EstagioFunil.ordem).all()

    def list_stages(self, tenant_id) -> list[PipelineStage]:
        return [
            PipelineStage(
                id=cid("stage", e.id),
                tenant_id=e.tenant_id,
                source=_src("estagio_funil", e.id),
                pipeline_id=cid("pipeline", tenant_id),
                name=e.nome,
                order=e.ordem,
                stage_type=_TIPO_ESTAGIO.get(e.tipo, StageType.OPEN),
            )
            for e in self._estagios(tenant_id)
        ]

    def list_opportunities(self, tenant_id, cursor=None, updated_since=None, limit=100) -> Page[Opportunity]:
        tipos = {e.id: _TIPO_ESTAGIO.get(e.tipo, StageType.OPEN) for e in self._estagios(tenant_id)}
        query = self._db.query(Negocio).filter(Negocio.tenant_id == tenant_id)
        if updated_since is not None:
            query = query.filter(Negocio.atualizado_em >= updated_since)
        negocios, proximo = _paginar(query, Negocio, cursor, limit)
        return Page[Opportunity](
            items=[
                Opportunity(
                    id=cid("opportunity", n.id),
                    tenant_id=n.tenant_id,
                    source=_src("negocio", n.id),
                    account_id=cid("account", n.conta_id),
                    primary_contact_id=cid("contact", n.decisor_id) if n.decisor_id else None,
                    owner_user_id=cid("user", n.vendedor_usuario_id) if n.vendedor_usuario_id else None,
                    pipeline_id=cid("pipeline", tenant_id),
                    stage_id=cid("stage", n.estagio_id),
                    name=n.nome,
                    amount=_money(n.valor),
                    probability=n.probabilidade,
                    status=_STATUS_OPORTUNIDADE[tipos.get(n.estagio_id, StageType.OPEN)],
                    offer_id=cid("offer", n.oferta_id) if n.oferta_id else None,
                    closed_at=n.ganho_em or n.perdido_em,
                    lost_reason=n.motivo_perda,
                    created_at=n.criado_em,
                    updated_at=n.atualizado_em,
                )
                for n in negocios
            ],
            next_cursor=proximo,
        )

    # --- Activity / Interaction / CSMetric -----------------------------------------
    def list_activities(self, tenant_id, cursor=None, limit=100) -> Page[Activity]:
        query = self._db.query(Atividade).filter(Atividade.tenant_id == tenant_id)
        atividades, proximo = _paginar(query, Atividade, cursor, limit)
        return Page[Activity](
            items=[
                Activity(
                    id=cid("activity", a.id),
                    tenant_id=a.tenant_id,
                    source=_src("atividade", a.id),
                    account_id=cid("account", a.conta_id) if a.conta_id else None,
                    opportunity_id=cid("opportunity", a.negocio_id) if a.negocio_id else None,
                    user_id=cid("user", a.usuario_id) if a.usuario_id else None,
                    kind=_TIPO_ATIVIDADE.get(a.tipo, ActivityKind.OTHER),
                    source_type=a.tipo,
                    description=a.descricao,
                    created_at=a.criado_em,
                )
                for a in atividades
            ],
            next_cursor=proximo,
        )

    def list_interactions(self, tenant_id, account_id=None, cursor=None, limit=100) -> Page[Interaction]:
        query = self._db.query(InteracaoConta).filter(InteracaoConta.tenant_id == tenant_id)
        if account_id is not None:
            query = query.filter(InteracaoConta.conta_id == int(account_id.rsplit(":", 1)[-1]))
        interacoes, proximo = _paginar(query, InteracaoConta, cursor, limit)
        return Page[Interaction](
            items=[
                Interaction(
                    id=cid("interaction", i.id),
                    tenant_id=i.tenant_id,
                    source=_src("interacao_conta", i.id),
                    account_id=cid("account", i.conta_id),
                    kind=i.tipo,
                    description=i.descricao,
                    created_at=i.criado_em,
                )
                for i in interacoes
            ],
            next_cursor=proximo,
        )

    def list_cs_metrics(self, tenant_id, cursor=None, limit=100) -> Page[CSMetric]:
        query = self._db.query(PesquisaNps).filter(PesquisaNps.tenant_id == tenant_id, PesquisaNps.nota.isnot(None))
        pesquisas, proximo = _paginar(query, PesquisaNps, cursor, limit)
        return Page[CSMetric](
            items=[
                CSMetric(
                    id=cid("cs_metric", p.id),
                    tenant_id=p.tenant_id,
                    source=_src("pesquisa_nps", p.id),
                    account_id=cid("account", p.conta_id),
                    metric="NPS",
                    value=float(p.nota),
                    scale_max=10.0,
                    collected_at=p.respondida_em,
                    created_at=p.criado_em,
                )
                for p in pesquisas
            ],
            next_cursor=proximo,
        )

    def list_offers(self, tenant_id) -> list[Offer]:
        ofertas = self._db.query(Oferta).filter(Oferta.tenant_id == tenant_id).order_by(Oferta.id).all()
        return [
            Offer(
                id=cid("offer", o.id),
                tenant_id=o.tenant_id,
                source=_src("oferta", o.id),
                name=o.nome,
                description=o.descricao,
                differentiators=list(o.diferenciais or []),
                proof_points=list(o.provas_sociais or []),
                icps=[cid("icp", o.icp_id)] if o.icp_id else [],
                price_min=_money(o.faixa_preco_min),
                price_max=_money(o.faixa_preco_max),
                active=o.ativo,
                created_at=o.criado_em,
            )
            for o in ofertas
        ]
