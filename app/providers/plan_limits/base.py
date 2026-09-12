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

    @abstractmethod
    def obter_limite_enriquecimento_site_semanal(self, tenant_id: str) -> int | None:
        """`None` = sem limite — todo plano hoje tem valor configurado,
        proporcional à franquia mensal (raio-X 2026-08-28); `None` fica
        reservado pra um plano futuro deliberadamente sem teto."""
        raise NotImplementedError

    @abstractmethod
    def obter_limite_enriquecimento_contatos_semanal(self, tenant_id: str) -> int | None:
        raise NotImplementedError

    # Recursos de escala (raio-X 2026-09-09) — gancho de upgrade além de
    # volume: só quem já opera em escala precisa deles (teste A/B,
    # auto-aprovação, webhook, API de parceiros, revenda), nunca o "core".
    @abstractmethod
    def permite_ab_teste_cadencia(self, tenant_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def permite_auto_aprovacao(self, tenant_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def permite_webhook_relatorio(self, tenant_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def permite_api_parceiros(self, tenant_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def permite_subtenants(self, tenant_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def permite_registro_oportunidade(self, tenant_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def obter_retencao_dias_relatorio(self, tenant_id: str) -> int | None:
        """`None` = sem limite."""
        raise NotImplementedError

    @abstractmethod
    def obter_retencao_dias_auditoria(self, tenant_id: str) -> int | None:
        raise NotImplementedError
