import pytest

from app.providers.plan_limits.stub import StubPlanLimitsProvider
from app.schemas.cadencia import CadenciaCreateSchema, ToqueCadenciaCreateSchema
from app.services import cadencia_service
from app.services.errors import RegraNegocioViolada

TENANT_ID = "tenant-teste"


def _dados_cadencia(ab_teste_no_primeiro_toque: bool) -> CadenciaCreateSchema:
    return CadenciaCreateSchema(
        nome="Cadência Teste",
        toques=[
            ToqueCadenciaCreateSchema(ordem=1, canal="email", ab_teste_habilitado=ab_teste_no_primeiro_toque),
            ToqueCadenciaCreateSchema(ordem=2, canal="whatsapp"),
            ToqueCadenciaCreateSchema(ordem=3, canal="email"),
            ToqueCadenciaCreateSchema(ordem=4, canal="whatsapp"),
            ToqueCadenciaCreateSchema(ordem=5, canal="email"),
        ],
    )


def test_ab_teste_bloqueado_pelo_plano_recusa(db_session):
    plan_limits = StubPlanLimitsProvider(recursos_desabilitados={TENANT_ID: {"ab_teste_cadencia"}})

    with pytest.raises(RegraNegocioViolada):
        cadencia_service.criar(db_session, TENANT_ID, "1", _dados_cadencia(True), plan_limits)


def test_ab_teste_permitido_pelo_plano_cria_normalmente(db_session):
    plan_limits = StubPlanLimitsProvider()

    cadencia = cadencia_service.criar(db_session, TENANT_ID, "1", _dados_cadencia(True), plan_limits)

    assert cadencia.id is not None


def test_sem_ab_teste_cria_mesmo_com_plano_restrito(db_session):
    """Plano sem o recurso não impede cadência nenhuma — só bloqueia quem
    tenta ligar o teste A/B de fato."""
    plan_limits = StubPlanLimitsProvider(recursos_desabilitados={TENANT_ID: {"ab_teste_cadencia"}})

    cadencia = cadencia_service.criar(db_session, TENANT_ID, "1", _dados_cadencia(False), plan_limits)

    assert cadencia.id is not None
