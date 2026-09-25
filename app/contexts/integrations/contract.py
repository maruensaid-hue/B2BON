"""Contrato de adapter do Integration Hub (Fase 2, Master Prompt §13).

Todo sistema externo (e o próprio CRM da B2B ON) entra por um adapter
que fala o modelo canônico. Os domínios (MAP, PREDATOR, Intelligence)
nunca fazem `if salesforce / if hubspot`: recebem um `CrmAdapter`.

Leitura é paginada por cursor opaco e aceita `updated_since` para sync
incremental. Escrita é opcional (capacidade declarada); um adapter que
não suporta uma operação levanta `OperacaoNaoSuportada`, nunca finge.
Auth, retries, rate limit, webhooks e registro de conectores são da
Fase 3; conectores externos reais, da Fase 13. Ver ADAPTER_CONTRACT.md.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

from app.contexts.shared.canonical.commercial import (
    Account,
    Activity,
    Contact,
    CSMetric,
    Customer,
    Interaction,
    Offer,
    Opportunity,
    Organization,
    Person,
    Pipeline,
    PipelineStage,
)

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    model_config = ConfigDict(frozen=True)

    items: list[T]
    next_cursor: str | None = None


class AdapterCapabilities(BaseModel):
    model_config = ConfigDict(frozen=True)

    system: str
    readable_entities: frozenset[str]
    writable_entities: frozenset[str] = frozenset()
    incremental_sync: bool = False
    webhooks: bool = False


class OperacaoNaoSuportada(Exception):
    """O adapter não suporta esta operação (capacidade não declarada)."""


class ErroTransitorio(Exception):
    """Falha que vale tentar de novo (429, 5xx, timeout)."""


class ErroCredencial(Exception):
    """Credencial inválida, expirada ou sem permissão (401/403). Não é
    transitória: tentar de novo só gasta cota e pode bloquear a conta."""


class CrmAdapter(ABC):
    """Porta de leitura/escrita de um CRM qualquer, em termos canônicos.

    Todo método recebe `tenant_id` e só pode devolver dados desse tenant
    (isolamento é responsabilidade do adapter, testado por contrato)."""

    @abstractmethod
    def capabilities(self) -> AdapterCapabilities: ...

    @abstractmethod
    def list_organizations(self, tenant_id: str, cursor: str | None = None, updated_since: datetime | None = None, limit: int = 100) -> Page[Organization]: ...

    @abstractmethod
    def list_accounts(self, tenant_id: str, cursor: str | None = None, updated_since: datetime | None = None, limit: int = 100) -> Page[Account]: ...

    @abstractmethod
    def list_customers(self, tenant_id: str, cursor: str | None = None, limit: int = 100) -> Page[Customer]: ...

    @abstractmethod
    def list_people(self, tenant_id: str, cursor: str | None = None, updated_since: datetime | None = None, limit: int = 100) -> Page[Person]: ...

    @abstractmethod
    def list_contacts(self, tenant_id: str, cursor: str | None = None, limit: int = 100) -> Page[Contact]: ...

    @abstractmethod
    def list_pipelines(self, tenant_id: str) -> list[Pipeline]: ...

    @abstractmethod
    def list_stages(self, tenant_id: str) -> list[PipelineStage]: ...

    @abstractmethod
    def list_opportunities(self, tenant_id: str, cursor: str | None = None, updated_since: datetime | None = None, limit: int = 100) -> Page[Opportunity]: ...

    @abstractmethod
    def list_activities(self, tenant_id: str, cursor: str | None = None, limit: int = 100) -> Page[Activity]: ...

    @abstractmethod
    def list_interactions(self, tenant_id: str, account_id: str | None = None, cursor: str | None = None, limit: int = 100) -> Page[Interaction]: ...

    @abstractmethod
    def list_cs_metrics(self, tenant_id: str, cursor: str | None = None, limit: int = 100) -> Page[CSMetric]: ...

    @abstractmethod
    def list_offers(self, tenant_id: str) -> list[Offer]: ...

    # --- Escrita (opcional) ------------------------------------------------
    def upsert_opportunity(self, tenant_id: str, opportunity: Opportunity) -> str:
        raise OperacaoNaoSuportada(f"{self.capabilities().system} não suporta escrita de Opportunity")

    def add_note(self, tenant_id: str, target_id: str, text: str) -> str:
        raise OperacaoNaoSuportada(f"{self.capabilities().system} não suporta escrita de notas")


def iterar_todos(listar, tenant_id: str, **kwargs) -> list:
    """Consome todas as páginas de um `list_*` paginado."""
    itens: list = []
    cursor = None
    while True:
        pagina = listar(tenant_id, cursor=cursor, **kwargs)
        itens.extend(pagina.items)
        if not pagina.next_cursor:
            return itens
        cursor = pagina.next_cursor


# --- Superfície pública do contexto para fora dele (Fase 3) ----------------------
def obter_registry():
    from app.contexts.integrations import registry

    return registry


def obter_sync():
    from app.contexts.integrations import sync

    return sync


def adapter_b2bon(db):
    from app.contexts.integrations.adapters.b2bon_crm import B2BOnCrmAdapter

    return B2BOnCrmAdapter(db)


def adapter_de_payload(tenant_id: str, **colecoes: list) -> CrmAdapter:
    from app.contexts.integrations.adapters.payload import PayloadCrmAdapter

    return PayloadCrmAdapter(tenant_id, **colecoes)
