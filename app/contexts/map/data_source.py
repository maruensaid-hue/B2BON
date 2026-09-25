"""Porta de entrada de dados do MAP (Fase 1, Master Prompt §7/§9/§13).

O MAP calcula saúde, churn e economia sobre dados comerciais que ele
NÃO é dono: contas, receita ganha, pipeline, custo de aquisição, NPS.
Antes da Fase 1 ele lia tudo isso direto do ORM do CRM/PREDATOR; agora
lê por esta porta. `CrmInternoMapDataSource` é a implementação sobre o
CRM da própria B2B ON; um CRM externo (Fase 13) vira outra implementação,
sem mudar o cálculo.
"""

from abc import ABC, abstractmethod

from sqlalchemy.orm import Session

from app.contexts.crm import contract as crm
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
