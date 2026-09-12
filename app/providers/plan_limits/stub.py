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
        recursos_desabilitados: dict[str, set[str]] | None = None,
        retencao_dias_relatorio: dict[str, int | None] | None = None,
        retencao_dias_auditoria: dict[str, int | None] | None = None,
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
        # Recursos de escala (raio-X 2026-09-09): sem override, o stub é
        # permissivo (todo recurso liberado, sem teto de retenção) — só
        # quem explicitamente testa um gate passa `tenant_id` em
        # `recursos_desabilitados` (ex.: {"tenant-x": {"ab_teste_cadencia"}}).
        # Testar comportamento real de plano restrito (POC/Starter) requer
        # `NucleoPlanLimitsProvider` com um `Plano` de verdade, não o stub.
        self._recursos_desabilitados = recursos_desabilitados or {}
        self._retencao_relatorio = retencao_dias_relatorio or {}
        self._retencao_auditoria = retencao_dias_auditoria or {}

    def obter_franquia_contas_mes(self, tenant_id: str) -> int:
        return self._overrides.get(tenant_id, self._franquia_padrao)

    def obter_limite_enriquecimento_site_semanal(self, tenant_id: str) -> int | None:
        return self._limite_site.get(tenant_id)

    def obter_limite_enriquecimento_contatos_semanal(self, tenant_id: str) -> int | None:
        return self._limite_contatos.get(tenant_id)

    def _permite(self, tenant_id: str, recurso: str) -> bool:
        return recurso not in self._recursos_desabilitados.get(tenant_id, set())

    def permite_ab_teste_cadencia(self, tenant_id: str) -> bool:
        return self._permite(tenant_id, "ab_teste_cadencia")

    def permite_auto_aprovacao(self, tenant_id: str) -> bool:
        return self._permite(tenant_id, "auto_aprovacao")

    def permite_webhook_relatorio(self, tenant_id: str) -> bool:
        return self._permite(tenant_id, "webhook_relatorio")

    def permite_api_parceiros(self, tenant_id: str) -> bool:
        return self._permite(tenant_id, "api_parceiros")

    def permite_subtenants(self, tenant_id: str) -> bool:
        return self._permite(tenant_id, "subtenants")

    def permite_registro_oportunidade(self, tenant_id: str) -> bool:
        return self._permite(tenant_id, "registro_oportunidade")

    def obter_retencao_dias_relatorio(self, tenant_id: str) -> int | None:
        return self._retencao_relatorio.get(tenant_id)

    def obter_retencao_dias_auditoria(self, tenant_id: str) -> int | None:
        return self._retencao_auditoria.get(tenant_id)
