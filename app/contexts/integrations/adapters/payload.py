"""Adapter em memória sobre dados canônicos enviados na própria requisição.

Permite que um cliente que usa outro CRM chame o MAP API enviando
contas/oportunidades/interações no formato canônico, sem conector
instalado (§11: "MAP API → EXTERNAL CRM"). O `tenant_id` dos itens é
SEMPRE sobrescrito pelo tenant da chave de API: o payload não consegue
se passar por outro tenant.
"""

from app.contexts.integrations.contract import AdapterCapabilities, CrmAdapter, Page

SYSTEM = "api_payload"


def _forcar_tenant(itens: list, tenant_id: str) -> list:
    return [item.model_copy(update={"tenant_id": tenant_id}) for item in itens]


class PayloadCrmAdapter(CrmAdapter):
    def __init__(self, tenant_id: str, **colecoes: list) -> None:
        self._tenant_id = tenant_id
        self._dados = {nome: _forcar_tenant(itens or [], tenant_id) for nome, itens in colecoes.items()}

    def _itens(self, nome: str, tenant_id: str) -> list:
        return self._dados.get(nome, []) if tenant_id == self._tenant_id else []

    def capabilities(self) -> AdapterCapabilities:
        return AdapterCapabilities(system=SYSTEM, readable_entities=frozenset(k for k, v in self._dados.items() if v))

    def _pagina(self, nome, tenant_id, cursor=None, **_):
        return Page(items=self._itens(nome, tenant_id), next_cursor=None)

    def list_organizations(self, tenant_id, cursor=None, updated_since=None, limit=100):
        return self._pagina("organizations", tenant_id)

    def list_accounts(self, tenant_id, cursor=None, updated_since=None, limit=100):
        return self._pagina("accounts", tenant_id)

    def list_customers(self, tenant_id, cursor=None, limit=100):
        return self._pagina("customers", tenant_id)

    def list_people(self, tenant_id, cursor=None, updated_since=None, limit=100):
        return self._pagina("people", tenant_id)

    def list_contacts(self, tenant_id, cursor=None, limit=100):
        return self._pagina("contacts", tenant_id)

    def list_pipelines(self, tenant_id):
        return self._itens("pipelines", tenant_id)

    def list_stages(self, tenant_id):
        return self._itens("stages", tenant_id)

    def list_opportunities(self, tenant_id, cursor=None, updated_since=None, limit=100):
        return self._pagina("opportunities", tenant_id)

    def list_activities(self, tenant_id, cursor=None, limit=100):
        return self._pagina("activities", tenant_id)

    def list_interactions(self, tenant_id, account_id=None, cursor=None, limit=100):
        itens = self._itens("interactions", tenant_id)
        if account_id is not None:
            itens = [i for i in itens if i.account_id == account_id]
        return Page(items=itens, next_cursor=None)

    def list_cs_metrics(self, tenant_id, cursor=None, limit=100):
        return self._pagina("cs_metrics", tenant_id)

    def list_offers(self, tenant_id):
        return self._itens("offers", tenant_id)
