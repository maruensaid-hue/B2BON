from abc import ABC, abstractmethod


class CrmProvider(ABC):
    """Porta para o CRM do núcleo B2B ON — dado que pertence ao núcleo, não
    ao PREDATOR (mesma regra de fronteira de `PlanLimitsProvider`)."""

    @abstractmethod
    def criar_ou_atualizar_oportunidade(self, tenant_id: str, conta_id: int, dados: dict) -> str:
        raise NotImplementedError

    @abstractmethod
    def anexar_nota(self, tenant_id: str, oportunidade_id: str, texto: str) -> None:
        raise NotImplementedError
