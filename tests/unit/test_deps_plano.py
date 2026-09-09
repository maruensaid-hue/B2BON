import pytest

from app.api.deps import exigir_plano_permite_api_parceiros
from app.models.usuario import Usuario
from app.providers.plan_limits.stub import StubPlanLimitsProvider
from app.services.errors import NaoAutorizado

TENANT_ID = "tenant-teste"


def _usuario() -> Usuario:
    return Usuario(id=1, tenant_id=TENANT_ID, nome="Admin", email="admin@teste.com.br", papel="admin", ativo=True)


def test_plano_sem_api_parceiros_recusa():
    plan_limits = StubPlanLimitsProvider(recursos_desabilitados={TENANT_ID: {"api_parceiros"}})

    with pytest.raises(NaoAutorizado):
        exigir_plano_permite_api_parceiros(usuario=_usuario(), plan_limits=plan_limits)


def test_plano_com_api_parceiros_libera():
    plan_limits = StubPlanLimitsProvider()

    resultado = exigir_plano_permite_api_parceiros(usuario=_usuario(), plan_limits=plan_limits)

    assert resultado.tenant_id == TENANT_ID
