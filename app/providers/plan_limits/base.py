from abc import ABC, abstractmethod


class PlanLimitsProvider(ABC):
    """Porta para limites de franquia do plano — dado que pertence ao núcleo
    B2B ON (planos/assinaturas), não ao PREDATOR (Seção 11 da especificação,
    "Integração com o núcleo").

    O PREDATOR só é responsável pelo enforcement e pelo contador de uso; a
    origem do limite (número de contas/mês por plano) é do núcleo.
    """

    @abstractmethod
    def obter_franquia_contas_mes(self, tenant_id: str) -> int:
        raise NotImplementedError
