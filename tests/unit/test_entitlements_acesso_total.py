from app.contexts.shared.entitlements import CAPACIDADES_PUBLIC_PROCUREMENT, MODULOS, Entitlements
from app.providers.plan_limits.stub import StubPlanLimitsProvider

TENANT = "tenant-x"
TODOS_BLOQUEADOS = {"map", "predator", "crm", "bids", "procurement", "sourcing"}


def _plano_sem_nada() -> StubPlanLimitsProvider:
    return StubPlanLimitsProvider(modulos_bloqueados={TENANT: TODOS_BLOQUEADOS | {"sourcing_enterprise"}})


def test_sem_acesso_total_segue_o_plano() -> None:
    entitlements = Entitlements(_plano_sem_nada(), TENANT)

    assert not any(entitlements.has_module(modulo) for modulo in MODULOS)
    assert not entitlements.has_capability("risk_engine")
    assert not entitlements.has_feature("SOURCING_ENTERPRISE")


def test_acesso_total_libera_todos_os_modulos_capacidades_e_o_sourcing_enterprise() -> None:
    entitlements = Entitlements(_plano_sem_nada(), TENANT, acesso_total=True)

    assert all(entitlements.has_module(modulo) for modulo in MODULOS)
    assert entitlements.has_any_module("bids", "procurement")
    assert all(entitlements.has_capability(c) for c in CAPACIDADES_PUBLIC_PROCUREMENT["FULL"])
    assert entitlements.has_feature("SOURCING_ENTERPRISE")


def test_acesso_total_nao_muda_limites_nem_os_outros_recursos_do_plano() -> None:
    """Só módulos/capacidades abrem; auto-aprovação, A/B e limite de usuários seguem o plano do tenant."""
    plano = StubPlanLimitsProvider(limite_usuarios={TENANT: 3})
    entitlements = Entitlements(plano, TENANT, acesso_total=True)

    assert entitlements.limite_usuarios() == 3
    assert entitlements.has_feature("AUTO_APROVACAO") == plano.permite_auto_aprovacao(TENANT)
    assert entitlements.has_feature("AB_TESTE_CADENCIA") == plano.permite_ab_teste_cadencia(TENANT)
