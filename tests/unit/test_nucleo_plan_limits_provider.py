from app.models.licenca import Licenca
from app.models.plano import Plano
from app.providers.plan_limits.nucleo import NucleoPlanLimitsProvider

TENANT_ID = "tenant-teste"


def test_franquia_reflete_plano_da_licenca_ativa(db_session):
    plano = Plano(nome="Starter", franquia_contas_mes=200, max_usuarios=10, preco_mensal=490.0)
    db_session.add(plano)
    db_session.flush()
    db_session.add(Licenca(tenant_id=TENANT_ID, plano_id=plano.id, status="ativa"))
    db_session.commit()

    provider = NucleoPlanLimitsProvider(db_session)

    assert provider.obter_franquia_contas_mes(TENANT_ID) == 200


def test_sem_licenca_retorna_zero(db_session):
    provider = NucleoPlanLimitsProvider(db_session)

    assert provider.obter_franquia_contas_mes("tenant-sem-licenca") == 0


def test_licenca_suspensa_nao_conta_como_ativa(db_session):
    plano = Plano(nome="Pro", franquia_contas_mes=800, max_usuarios=25, preco_mensal=990.0)
    db_session.add(plano)
    db_session.flush()
    db_session.add(Licenca(tenant_id=TENANT_ID, plano_id=plano.id, status="suspensa"))
    db_session.commit()

    provider = NucleoPlanLimitsProvider(db_session)

    assert provider.obter_franquia_contas_mes(TENANT_ID) == 0
