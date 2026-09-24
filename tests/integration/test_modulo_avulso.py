from app.api.deps import get_plan_limits_provider
from app.main import app
from app.providers.plan_limits.stub import StubPlanLimitsProvider

TENANT_ID = "tenant-teste"


def test_tenant_com_todos_os_modulos_acessa_map_crm_predator(client):
    """Sanity check do default permissivo do stub — a suíte inteira de
    testes existente depende disso pra não quebrar (raio-X 2026-09-24)."""
    assert client.get("/api/v1/saude-contas/dashboard").status_code == 200
    assert client.get("/api/v1/crm/estagios").status_code == 200
    assert client.get("/api/v1/icp").status_code == 200


def test_tenant_so_com_map_e_bloqueado_em_crm_e_predator(client, monkeypatch):
    """Tenant com um plano avulso "MAP Starter" (sem predator/crm) recebe
    403 nas rotas dos outros dois módulos, mas continua acessando o MAP."""
    monkeypatch.setitem(
        app.dependency_overrides,
        get_plan_limits_provider,
        lambda: StubPlanLimitsProvider(modulos_bloqueados={TENANT_ID: {"predator", "crm"}}),
    )

    assert client.get("/api/v1/saude-contas/dashboard").status_code == 200
    assert client.get("/api/v1/crm/estagios").status_code == 403
    assert client.get("/api/v1/icp").status_code == 403


def test_tenant_so_com_predator_e_bloqueado_em_map_e_crm(client, monkeypatch):
    monkeypatch.setitem(
        app.dependency_overrides,
        get_plan_limits_provider,
        lambda: StubPlanLimitsProvider(modulos_bloqueados={TENANT_ID: {"map", "crm"}}),
    )

    assert client.get("/api/v1/icp").status_code == 200
    assert client.get("/api/v1/saude-contas/dashboard").status_code == 403
    assert client.get("/api/v1/crm/estagios").status_code == 403
