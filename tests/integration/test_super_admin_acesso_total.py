"""O super_admin (operador da plataforma) usa todos os módulos mesmo com plano sem eles; cliente só o que o plano libera."""

import pytest

from app.api.deps import get_plan_limits_provider
from app.core.config import settings
from app.main import app
from app.providers.plan_limits.stub import StubPlanLimitsProvider

TENANT_ID = "tenant-teste"
NOVOS = {"bids", "procurement", "sourcing"}
ROTAS = ("/api/v1/bids/licitacoes", "/api/v1/procurement/metricas", "/api/v1/sourcing/processos")


@pytest.fixture()
def plano_sem_os_novos_modulos(monkeypatch):
    monkeypatch.setitem(
        app.dependency_overrides,
        get_plan_limits_provider,
        lambda: StubPlanLimitsProvider(modulos_bloqueados={TENANT_ID: NOVOS}),
    )


@pytest.fixture()
def acesso_total_ligado(monkeypatch):
    monkeypatch.setattr(settings, "super_admin_acesso_total_modulos", True)


@pytest.mark.parametrize("rota", ROTAS)
def test_super_admin_acessa_modulo_fora_do_plano(client, plano_sem_os_novos_modulos, acesso_total_ligado, rota):
    assert client.get(rota).status_code == 200


def test_super_admin_acessa_capacidade_do_procurement_fora_do_plano(client, plano_sem_os_novos_modulos, acesso_total_ligado):
    assert client.get("/api/v1/procurement/riscos").status_code == 200


@pytest.mark.parametrize("papel", ["admin", "user"])
@pytest.mark.parametrize("rota", ROTAS)
def test_cliente_do_mesmo_tenant_segue_o_plano(
    client, criar_usuario_autenticado, plano_sem_os_novos_modulos, acesso_total_ligado, papel, rota
):
    headers = criar_usuario_autenticado(TENANT_ID, papel=papel, email=f"{papel}@acesso-total.com.br")

    assert client.get(rota, headers=headers).status_code == 403


@pytest.mark.parametrize("rota", ROTAS)
def test_com_a_chave_desligada_o_super_admin_segue_o_plano(client, plano_sem_os_novos_modulos, monkeypatch, rota):
    monkeypatch.setattr(settings, "super_admin_acesso_total_modulos", False)

    assert client.get(rota).status_code == 403


def test_menu_do_login_mostra_todos_os_modulos_so_ao_super_admin(client, criar_usuario_autenticado, acesso_total_ligado):
    """/auth/eu usa o plano real do tenant (módulos map/predator/crm): o super_admin ganha os demais no menu."""
    super_admin = client.get("/api/v1/auth/eu").json()["recursos_plano"]
    assert all(super_admin[f"modulo_{m}"] for m in ("map", "predator", "crm", "bids", "procurement", "sourcing"))

    headers = criar_usuario_autenticado(TENANT_ID, papel="admin", email="admin-menu@acesso-total.com.br")
    cliente = client.get("/api/v1/auth/eu", headers=headers).json()["recursos_plano"]
    assert cliente["modulo_crm"] is True
    assert not any(cliente[f"modulo_{m}"] for m in NOVOS)


def test_menu_do_cliente_nao_muda_com_a_chave_desligada(client, monkeypatch):
    monkeypatch.setattr(settings, "super_admin_acesso_total_modulos", False)

    recursos = client.get("/api/v1/auth/eu").json()["recursos_plano"]

    assert not any(recursos[f"modulo_{m}"] for m in NOVOS)
