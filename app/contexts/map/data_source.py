"""Porta de entrada de dados do MAP (Fase 1, Master Prompt §7/§9/§13).

O MAP calcula saúde, churn e economia sobre dados comerciais que ele
NÃO é dono: contas, receita ganha, pipeline, custo de aquisição, NPS.
Antes da Fase 1 ele lia tudo isso direto do ORM do CRM/PREDATOR; agora
lê por esta porta. `CrmInternoMapDataSource` é a implementação sobre o
CRM da própria B2B ON; um CRM externo (Fase 13) vira outra implementação,
sem mudar o cálculo.
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.contexts.crm import contract as crm
from app.contexts.integrations.contract import CrmAdapter, iterar_todos
from app.contexts.map.interacoes import listar_interacoes
from app.contexts.shared.canonical.commercial import OpportunityStatus, StageType
from app.contexts.shared.organizations import OrganizationRef, listar_organizacoes
from app.models.pesquisa_nps import PesquisaNps


class MapDataSource(ABC):
    @abstractmethod
    def contas(
        self, tenant_id: str, vendedor_usuario_id: int | None = None, apenas_com_vendedor: bool = False
    ) -> list[OrganizationRef]: ...

    @abstractmethod
    def valor_ganho_por_conta(self, tenant_id: str, conta_ids: list[int]) -> dict[int, float]: ...

    @abstractmethod
    def valor_pipeline_aberto(self, tenant_id: str, conta_id: int) -> float: ...

    @abstractmethod
    def custo_aquisicao(self, tenant_id: str, periodo: str) -> float | None: ...

    @abstractmethod
    def notas_nps(self, tenant_id: str, conta_ids: list[int]) -> list[int]: ...

    @abstractmethod
    def funil(self, tenant_id: str, vendedor_usuario_id: int | None = None) -> dict: ...

    @abstractmethod
    def interacoes(self, tenant_id: str, conta_id: int | str) -> list:
        """Sinais de relacionamento da conta, mais recente primeiro. Cada
        item tem `tipo` e `criado_em`."""


class CrmInternoMapDataSource(MapDataSource):
    def __init__(self, db: Session) -> None:
        self._db = db

    def contas(
        self, tenant_id: str, vendedor_usuario_id: int | None = None, apenas_com_vendedor: bool = False
    ) -> list[OrganizationRef]:
        return listar_organizacoes(self._db, tenant_id, vendedor_usuario_id, apenas_com_vendedor)

    def valor_ganho_por_conta(self, tenant_id: str, conta_ids: list[int]) -> dict[int, float]:
        return crm.valor_ganho_por_conta(self._db, tenant_id, conta_ids)

    def valor_pipeline_aberto(self, tenant_id: str, conta_id: int) -> float:
        return crm.valor_pipeline_aberto(self._db, tenant_id, conta_id)

    def custo_aquisicao(self, tenant_id: str, periodo: str) -> float | None:
        return crm.custo_aquisicao(self._db, tenant_id, periodo)

    def notas_nps(self, tenant_id: str, conta_ids: list[int]) -> list[int]:
        if not conta_ids:
            return []
        linhas = (
            self._db.query(PesquisaNps.nota)
            .filter(
                PesquisaNps.tenant_id == tenant_id,
                PesquisaNps.conta_id.in_(conta_ids),
                PesquisaNps.nota.isnot(None),
            )
            .all()
        )
        return [nota for (nota,) in linhas]

    def funil(self, tenant_id: str, vendedor_usuario_id: int | None = None) -> dict:
        return crm.funil(self._db, tenant_id, vendedor_usuario_id)

    def interacoes(self, tenant_id: str, conta_id: int | str) -> list:
        return listar_interacoes(self._db, tenant_id, int(conta_id))


@dataclass(frozen=True)
class _InteracaoCanonica:
    tipo: str
    criado_em: datetime


_TIPO_ESTAGIO_INTERNO = {StageType.OPEN: "aberto", StageType.WON: "ganho", StageType.LOST: "perdido"}


class CanonicalMapDataSource(MapDataSource):
    """MAP sobre o modelo canônico (Fase 2): qualquer `CrmAdapter` — o da
    própria B2B ON ou, na Fase 13, Salesforce/HubSpot/Pipedrive/RD —
    alimenta o mesmo cálculo de saúde e economia.

    Ids de conta aqui são os ids canônicos de `Account`. Custo de
    aquisição não existe em CRM de mercado: vem de `custo_aquisicao`
    (tipicamente o valor lançado no próprio MAP) ou fica `None`."""

    def __init__(self, adapter: CrmAdapter, custo_aquisicao: Callable[[str, str], float | None] | None = None) -> None:
        self._adapter = adapter
        self._custo = custo_aquisicao

    def contas(
        self, tenant_id: str, vendedor_usuario_id: int | str | None = None, apenas_com_vendedor: bool = False
    ) -> list[OrganizationRef]:
        organizacoes = {o.id: o for o in iterar_todos(self._adapter.list_organizations, tenant_id)}
        clientes = {c.account_id: c for c in iterar_todos(self._adapter.list_customers, tenant_id)}
        resultado = []
        for conta in iterar_todos(self._adapter.list_accounts, tenant_id):
            if vendedor_usuario_id is not None and conta.owner_user_id != vendedor_usuario_id:
                continue
            if apenas_com_vendedor and conta.owner_user_id is None:
                continue
            org = organizacoes.get(conta.organization_id)
            cliente = clientes.get(conta.id)
            resultado.append(
                OrganizationRef(
                    id=conta.id,
                    tenant_id=conta.tenant_id,
                    nome=org.legal_name if org else conta.id,
                    nome_fantasia=org.trade_name if org else None,
                    cnpj=org.tax_id if org else None,
                    dominio=org.domain if org else None,
                    vendedor_usuario_id=conta.owner_user_id,
                    cliente_desde=cliente.customer_since if cliente else None,
                    cliente_cancelado_em=cliente.churned_at if cliente else None,
                    criado_em=conta.created_at,
                )
            )
        return resultado

    def _oportunidades(self, tenant_id: str):
        return iterar_todos(self._adapter.list_opportunities, tenant_id)

    def _somar(self, tenant_id: str, status: OpportunityStatus, conta_ids: set) -> dict:
        totais: dict = {}
        for oportunidade in self._oportunidades(tenant_id):
            if oportunidade.status != status or oportunidade.account_id not in conta_ids or oportunidade.amount is None:
                continue
            totais[oportunidade.account_id] = totais.get(oportunidade.account_id, 0.0) + float(oportunidade.amount.amount)
        return totais

    def valor_ganho_por_conta(self, tenant_id: str, conta_ids: list) -> dict:
        return self._somar(tenant_id, OpportunityStatus.WON, set(conta_ids))

    def valor_pipeline_aberto(self, tenant_id: str, conta_id) -> float:
        return self._somar(tenant_id, OpportunityStatus.OPEN, {conta_id}).get(conta_id, 0.0)

    def custo_aquisicao(self, tenant_id: str, periodo: str) -> float | None:
        return self._custo(tenant_id, periodo) if self._custo else None

    def notas_nps(self, tenant_id: str, conta_ids: list) -> list[int]:
        ids = set(conta_ids)
        return [
            metrica.value
            for metrica in iterar_todos(self._adapter.list_cs_metrics, tenant_id)
            if metrica.metric == "NPS" and metrica.value is not None and metrica.account_id in ids
        ]

    def funil(self, tenant_id: str, vendedor_usuario_id=None) -> dict:
        oportunidades = [
            o for o in self._oportunidades(tenant_id)
            if vendedor_usuario_id is None or o.owner_user_id == vendedor_usuario_id
        ]
        estagios = []
        for estagio in self._adapter.list_stages(tenant_id):
            do_estagio = [o for o in oportunidades if o.stage_id == estagio.id]
            estagios.append(
                {
                    "estagio_id": estagio.id,
                    "nome": estagio.name,
                    "tipo": _TIPO_ESTAGIO_INTERNO[estagio.stage_type],
                    "quantidade": len(do_estagio),
                    "valor_total": sum(float(o.amount.amount) for o in do_estagio if o.amount is not None),
                }
            )
        total = len(oportunidades)
        ganhos = sum(1 for o in oportunidades if o.status == OpportunityStatus.WON)
        return {"estagios": estagios, "taxa_conversao": ganhos / total if total else None}

    def interacoes(self, tenant_id: str, conta_id) -> list:
        itens = iterar_todos(self._adapter.list_interactions, tenant_id, account_id=conta_id)
        convertidas = [_InteracaoCanonica(tipo=i.kind, criado_em=i.created_at) for i in itens if i.created_at is not None]
        return sorted(convertidas, key=lambda i: i.criado_em, reverse=True)
