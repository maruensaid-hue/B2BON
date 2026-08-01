from app.providers.plan_limits.base import PlanLimitsProvider


class CoreApiPlanLimitsProvider(PlanLimitsProvider):
    """Cliente do núcleo B2B ON para limites de franquia por plano.

    Assinatura mantida estável para que o PREDATOR já dependa da porta
    `PlanLimitsProvider`, não desta implementação. O corpo é implementado
    quando o núcleo expuser o endpoint de franquias — até lá, todo ambiente
    (dev e testes) usa `StubPlanLimitsProvider`.
    """

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    def obter_franquia_contas_mes(self, tenant_id: str) -> int:
        raise NotImplementedError(
            "Integração com o núcleo B2B ON ainda não implementada. "
            "Use StubPlanLimitsProvider em desenvolvimento e testes."
        )
