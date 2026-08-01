import pytest

from app.models.conta import Conta
from app.models.icp import ICP
from app.providers.plan_limits.stub import StubPlanLimitsProvider
from app.services import franquia_service
from app.services.errors import RegraNegocioViolada

TENANT_ID = "tenant-teste"


@pytest.fixture()
def contas_de_teste(db_session):
    icp = ICP(
        tenant_id=TENANT_ID, grupo_id="grupo-1", nome="ICP", segmento="Tecnologia", porte="PEQUENO",
        regiao="SP", ativo=True,
    )
    db_session.add(icp)
    db_session.flush()

    contas = [
        Conta(tenant_id=TENANT_ID, icp_id=icp.id, nome=f"Conta {i}", status="prospectada")
        for i in range(3)
    ]
    db_session.add_all(contas)
    db_session.commit()
    return contas


def test_geracao_nao_consome_franquia(db_session, contas_de_teste):
    """E2-H1: gerar/avaliar/descartar listas não consome franquia."""
    plan_limits = StubPlanLimitsProvider(franquia_padrao=10)

    franquia = franquia_service.obter_franquia(db_session, TENANT_ID, plan_limits)

    assert franquia == {"limite": 10, "usado": 0, "restante": 10}


def test_consumir_para_ativacao_registra_uso(db_session, contas_de_teste):
    plan_limits = StubPlanLimitsProvider(franquia_padrao=10)
    conta_ids = [c.id for c in contas_de_teste[:2]]

    resultado = franquia_service.consumir_para_ativacao(db_session, TENANT_ID, "ator-1", conta_ids, plan_limits)

    assert resultado == {"limite": 10, "usado": 2, "restante": 8}


def test_consumo_e_idempotente_na_mesma_janela_mensal(db_session, contas_de_teste):
    """Mesma conta incluída duas vezes na mesma janela mensal não consome duas vezes."""
    plan_limits = StubPlanLimitsProvider(franquia_padrao=10)
    conta_id = contas_de_teste[0].id

    franquia_service.consumir_para_ativacao(db_session, TENANT_ID, "ator-1", [conta_id], plan_limits)
    resultado = franquia_service.consumir_para_ativacao(db_session, TENANT_ID, "ator-1", [conta_id], plan_limits)

    assert resultado["usado"] == 1


def test_consumir_para_ativacao_bloqueia_ao_exceder_limite(db_session, contas_de_teste):
    """No limite, novas ativações bloqueiam com aviso — nada é consumido."""
    plan_limits = StubPlanLimitsProvider(franquia_padrao=1)
    conta_ids = [c.id for c in contas_de_teste[:2]]

    with pytest.raises(RegraNegocioViolada):
        franquia_service.consumir_para_ativacao(db_session, TENANT_ID, "ator-1", conta_ids, plan_limits)

    franquia = franquia_service.obter_franquia(db_session, TENANT_ID, plan_limits)
    assert franquia["usado"] == 0  # bloqueio é tudo-ou-nada; nenhuma conta foi consumida


def test_ativacao_ja_consumida_nao_e_bloqueada_por_cota_futura(db_session, contas_de_teste):
    """Cadências já ativas seguem até o fim — não há mecanismo que revogue
    consumo já registrado quando a franquia se esgota depois."""
    plan_limits_generoso = StubPlanLimitsProvider(franquia_padrao=10)
    conta_id = contas_de_teste[0].id
    franquia_service.consumir_para_ativacao(db_session, TENANT_ID, "ator-1", [conta_id], plan_limits_generoso)

    plan_limits_apertado = StubPlanLimitsProvider(franquia_padrao=0)
    franquia = franquia_service.obter_franquia(db_session, TENANT_ID, plan_limits_apertado)

    assert franquia["usado"] == 1  # consumo permanece registrado, não é desfeito
