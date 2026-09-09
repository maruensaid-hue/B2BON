from datetime import UTC, datetime, timedelta

import pytest

from app.providers.plan_limits.stub import StubPlanLimitsProvider
from app.services import auditoria_service
from app.services.errors import RegraNegocioViolada

TENANT_ID = "tenant-teste"


def test_sem_retencao_no_plano_devolve_tudo(db_session):
    auditoria_service.registrar(db_session, TENANT_ID, "evento_antigo", "teste", 1)

    logs = auditoria_service.consultar(db_session, TENANT_ID, StubPlanLimitsProvider())

    assert len(logs) == 1


def test_data_inicio_explicito_mais_antigo_que_retencao_recusa(db_session):
    plan_limits = StubPlanLimitsProvider(retencao_dias_auditoria={TENANT_ID: 30})
    data_inicio_muito_antiga = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=90)

    with pytest.raises(RegraNegocioViolada):
        auditoria_service.consultar(db_session, TENANT_ID, plan_limits, data_inicio=data_inicio_muito_antiga)


def test_sem_data_inicio_e_com_retencao_so_limita_sem_erro(db_session):
    auditoria_service.registrar(db_session, TENANT_ID, "evento", "teste", 1)
    plan_limits = StubPlanLimitsProvider(retencao_dias_auditoria={TENANT_ID: 30})

    logs = auditoria_service.consultar(db_session, TENANT_ID, plan_limits)

    assert len(logs) == 1


def test_data_inicio_dentro_da_retencao_funciona(db_session):
    plan_limits = StubPlanLimitsProvider(retencao_dias_auditoria={TENANT_ID: 30})
    data_inicio_recente = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=5)

    logs = auditoria_service.consultar(db_session, TENANT_ID, plan_limits, data_inicio=data_inicio_recente)

    assert logs == []
