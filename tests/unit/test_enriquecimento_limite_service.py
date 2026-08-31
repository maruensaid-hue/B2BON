import pytest

from app.models.enriquecimento_semanal_consumo import EnriquecimentoSemanalConsumo
from app.providers.plan_limits.stub import StubPlanLimitsProvider
from app.services import enriquecimento_limite_service
from app.services.errors import RegraNegocioViolada

TENANT_ID = "tenant-limite-enriquecimento"


def test_sem_limite_configurado_nunca_bloqueia(db_session):
    """Plano pago (limite None) — libera sem registrar nada."""
    plan_limits = StubPlanLimitsProvider()

    for _ in range(200):
        enriquecimento_limite_service.verificar_e_registrar(db_session, TENANT_ID, "site", plan_limits)

    assert db_session.query(EnriquecimentoSemanalConsumo).count() == 0


def test_limite_atingido_bloqueia_com_regra_de_negocio(db_session):
    plan_limits = StubPlanLimitsProvider(limite_enriquecimento_site_semanal={TENANT_ID: 3})

    for _ in range(3):
        enriquecimento_limite_service.verificar_e_registrar(db_session, TENANT_ID, "site", plan_limits)

    with pytest.raises(RegraNegocioViolada):
        enriquecimento_limite_service.verificar_e_registrar(db_session, TENANT_ID, "site", plan_limits)

    assert db_session.query(EnriquecimentoSemanalConsumo).filter_by(tenant_id=TENANT_ID, tipo="site").count() == 3


def test_contadores_de_site_e_contatos_sao_independentes(db_session):
    plan_limits = StubPlanLimitsProvider(
        limite_enriquecimento_site_semanal={TENANT_ID: 1},
        limite_enriquecimento_contatos_semanal={TENANT_ID: 1},
    )

    enriquecimento_limite_service.verificar_e_registrar(db_session, TENANT_ID, "site", plan_limits)
    with pytest.raises(RegraNegocioViolada):
        enriquecimento_limite_service.verificar_e_registrar(db_session, TENANT_ID, "site", plan_limits)

    # "contatos" não foi afetado pelo esgotamento de "site"
    enriquecimento_limite_service.verificar_e_registrar(db_session, TENANT_ID, "contatos", plan_limits)
    with pytest.raises(RegraNegocioViolada):
        enriquecimento_limite_service.verificar_e_registrar(db_session, TENANT_ID, "contatos", plan_limits)


def test_semana_diferente_reseta_o_contador(db_session, monkeypatch):
    plan_limits = StubPlanLimitsProvider(limite_enriquecimento_site_semanal={TENANT_ID: 1})

    monkeypatch.setattr(enriquecimento_limite_service, "_semana_atual", lambda: "2026-W35")
    enriquecimento_limite_service.verificar_e_registrar(db_session, TENANT_ID, "site", plan_limits)
    with pytest.raises(RegraNegocioViolada):
        enriquecimento_limite_service.verificar_e_registrar(db_session, TENANT_ID, "site", plan_limits)

    monkeypatch.setattr(enriquecimento_limite_service, "_semana_atual", lambda: "2026-W36")
    # Semana nova, contador zerado de novo — não levanta.
    enriquecimento_limite_service.verificar_e_registrar(db_session, TENANT_ID, "site", plan_limits)


def test_obter_limites_sem_plano_configurado_retorna_none_em_tudo(db_session):
    plan_limits = StubPlanLimitsProvider()

    limites = enriquecimento_limite_service.obter_limites(db_session, TENANT_ID, plan_limits)

    assert limites == {
        "site": {"limite": None, "usado": 0, "restante": None},
        "contatos": {"limite": None, "usado": 0, "restante": None},
    }


def test_obter_limites_com_plano_configurado_reflete_uso(db_session):
    plan_limits = StubPlanLimitsProvider(
        limite_enriquecimento_site_semanal={TENANT_ID: 50},
        limite_enriquecimento_contatos_semanal={TENANT_ID: 50},
    )
    enriquecimento_limite_service.verificar_e_registrar(db_session, TENANT_ID, "site", plan_limits)
    enriquecimento_limite_service.verificar_e_registrar(db_session, TENANT_ID, "site", plan_limits)

    limites = enriquecimento_limite_service.obter_limites(db_session, TENANT_ID, plan_limits)

    assert limites["site"] == {"limite": 50, "usado": 2, "restante": 48}
    assert limites["contatos"] == {"limite": 50, "usado": 0, "restante": 50}
