from app.core.config import settings
from app.providers.plan_limits.base import PlanLimitsProvider


class StubPlanLimitsProvider(PlanLimitsProvider):
    """Implementação de desenvolvimento/teste da porta de franquias.

    Usada enquanto o núcleo B2B ON não está disponível para integração
    (Seção 1 do backlog, "Regra de fronteira"). Os valores nunca representam
    uma decisão comercial real — são apenas o necessário para exercitar o
    enforcement de franquia do PREDATOR de ponta a ponta.
    """

    def __init__(
        self,
        franquia_padrao: int | None = None,
        overrides: dict[str, int] | None = None,
        limite_enriquecimento_site_semanal: dict[str, int | None] | None = None,
        limite_enriquecimento_contatos_semanal: dict[str, int | None] | None = None,
    ) -> None:
        self._franquia_padrao = (
            franquia_padrao if franquia_padrao is not None else settings.franquia_contas_mes_stub_default
        )
        self._overrides = overrides or {}
        # Sem override, testes não têm limite semanal — só quem
        # explicitamente testa o bloqueio de algum plano passa um
        # override (todo plano real tem limite configurado hoje, mas o
        # default do stub continua sem teto pra não exigir override em
        # todo teste que nem toca nesse comportamento).
        self._limite_site = limite_enriquecimento_site_semanal or {}
        self._limite_contatos = limite_enriquecimento_contatos_semanal or {}

    def obter_franquia_contas_mes(self, tenant_id: str) -> int:
        return self._overrides.get(tenant_id, self._franquia_padrao)

    def obter_limite_enriquecimento_site_semanal(self, tenant_id: str) -> int | None:
        return self._limite_site.get(tenant_id)

    def obter_limite_enriquecimento_contatos_semanal(self, tenant_id: str) -> int | None:
        return self._limite_contatos.get(tenant_id)
