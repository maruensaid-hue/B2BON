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
    def obter_limite_usuarios(self, tenant_id: str) -> int | None:
        """Assentos internos do tenant (Phase J3, OI-023): usuários incluídos no plano (`max_usuarios`) +
        usuários adicionais contratados na licença (`usuarios_adicionais`, preço PENDING_DEFINITION).
        `None` = sem limite (plano sem teto ou tenant sem licença ativa, como antes)."""
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

    @abstractmethod
    def obter_limite_cadencias_mes(self, tenant_id: str) -> int | None:
        """`None` = sem limite — mesma semântica dos limites de
        enriquecimento acima, mas de ciclo mensal (raio-X 2026-09-22)."""
        raise NotImplementedError

    @abstractmethod
    def obter_limite_campanhas_mes(self, tenant_id: str) -> int | None:
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

    @abstractmethod
    def permite_modulo(self, tenant_id: str, modulo: str) -> bool:
        """Contratação avulsa por módulo (raio-X 2026-09-24) — `modulo` é
        "map"/"predator"/"crm". Todo plano de suíte libera os três; um
        plano avulso libera só o(s) módulo(s) contratado(s). Sem licença
        ativa nenhuma, `False` pra qualquer módulo (mesmo padrão de
        `obter_limite_enriquecimento_*`: ausência de plano bloqueia, não
        libera)."""
        raise NotImplementedError
