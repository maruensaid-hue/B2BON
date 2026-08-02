from abc import ABC, abstractmethod


class RedeSocialProvider(ABC):
    """Porta para a Rede Social B2B do núcleo — dado que pertence ao
    núcleo, não ao PREDATOR (mesma regra de fronteira de `CrmProvider`/
    `PlanLimitsProvider`). Usada para identificar indicações intra-rede
    (E11-H3)."""

    @abstractmethod
    def eh_assinante(self, identificador: str) -> bool:
        raise NotImplementedError
