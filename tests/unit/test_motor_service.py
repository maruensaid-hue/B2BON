from datetime import UTC, datetime, timedelta

import pytest

from app.models.interacao_tenant import InteracaoTenant
from app.models.licenca import Licenca
from app.models.plano import Plano
from app.models.tenant import Tenant
from app.services import motor_service
from app.services.errors import NaoEncontrado, ValidacaoFalhou

TENANT_ID = "tenant-motor"
ATOR_ID = "1"


def _agora_menos_dias(dias: int) -> datetime:
    return datetime.now(UTC).replace(tzinfo=None) - timedelta(days=dias)


def _criar_tenant(db_session, tenant_id: str = TENANT_ID, preco_mensal: float = 500.0) -> Tenant:
    tenant = Tenant(id=tenant_id, razao_social="Empresa Motor Teste")
    db_session.add(tenant)
    plano = Plano(nome=f"Plano-{tenant_id}", franquia_contas_mes=200, max_usuarios=5, preco_mensal=preco_mensal)
    db_session.add(plano)
    db_session.flush()
    db_session.add(Licenca(tenant_id=tenant_id, plano_id=plano.id, status="ativa"))
    db_session.commit()
    return tenant


def test_registrar_interacao_tipo_invalido_falha(db_session):
    _criar_tenant(db_session)

    with pytest.raises(ValidacaoFalhou):
        motor_service.registrar_interacao(db_session, TENANT_ID, ATOR_ID, "tipo-invalido")


def test_registrar_interacao_tenant_inexistente_falha(db_session):
    with pytest.raises(NaoEncontrado):
        motor_service.registrar_interacao(db_session, "tenant-fantasma", ATOR_ID, "contato")


def test_registrar_interacao_persiste(db_session):
    _criar_tenant(db_session)

    interacao = motor_service.registrar_interacao(db_session, TENANT_ID, ATOR_ID, "reclamacao", "Cliente insatisfeito")

    assert interacao.id is not None
    assert interacao.criado_por_usuario_id == 1
    assert motor_service.listar_interacoes(db_session, TENANT_ID) == [interacao]


def test_score_risco_tenant_inexistente_falha(db_session):
    with pytest.raises(NaoEncontrado):
        motor_service.calcular_score_risco(db_session, "tenant-fantasma")


def test_score_risco_sem_interacao_usa_data_inicio_da_licenca(db_session):
    _criar_tenant(db_session)
    licenca = db_session.query(Licenca).filter_by(tenant_id=TENANT_ID).one()
    licenca.data_inicio = _agora_menos_dias(40)
    db_session.commit()

    resultado = motor_service.calcular_score_risco(db_session, TENANT_ID)

    assert resultado["dias_sem_contato"] >= 39
    assert resultado["sinais"]["dias_sem_contato"] == 30
    assert resultado["score"] == 40.0  # base 10 + 30
    assert resultado["classificacao"] == "saudavel"  # 40 < limiar_risco_atencao_tenant (45)


@pytest.mark.parametrize(
    ("dias", "pontos_esperados"),
    [(35, 30), (20, 20), (10, 10)],
)
def test_score_risco_sobe_conforme_dias_sem_contato(db_session, dias, pontos_esperados):
    _criar_tenant(db_session)
    db_session.add(InteracaoTenant(tenant_id=TENANT_ID, tipo="contato", criado_em=_agora_menos_dias(dias)))
    db_session.commit()

    resultado = motor_service.calcular_score_risco(db_session, TENANT_ID)

    assert resultado["sinais"]["dias_sem_contato"] == pontos_esperados
    assert resultado["score"] == 10.0 + pontos_esperados


def test_score_risco_com_poucos_dias_sem_contato_nao_soma_pontos(db_session):
    _criar_tenant(db_session)
    db_session.add(InteracaoTenant(tenant_id=TENANT_ID, tipo="contato", criado_em=_agora_menos_dias(1)))
    db_session.commit()

    resultado = motor_service.calcular_score_risco(db_session, TENANT_ID)

    assert "dias_sem_contato" not in resultado["sinais"]
    assert resultado["score"] == 10.0
    assert resultado["classificacao"] == "saudavel"


def test_score_risco_reclamacoes_recentes_tem_limite_de_pontos(db_session):
    _criar_tenant(db_session)
    db_session.add(InteracaoTenant(tenant_id=TENANT_ID, tipo="contato", criado_em=_agora_menos_dias(1)))
    for _ in range(5):
        db_session.add(InteracaoTenant(tenant_id=TENANT_ID, tipo="reclamacao", criado_em=_agora_menos_dias(2)))
    db_session.commit()

    resultado = motor_service.calcular_score_risco(db_session, TENANT_ID)

    assert resultado["sinais"]["reclamacoes"] == 45  # 5 * 15 = 75, limitado a 45
    assert resultado["score"] == 55.0  # base 10 + 45
    assert resultado["classificacao"] == "atencao"


def test_score_risco_reclamacoes_antigas_nao_contam(db_session):
    _criar_tenant(db_session)
    db_session.add(InteracaoTenant(tenant_id=TENANT_ID, tipo="contato", criado_em=_agora_menos_dias(1)))
    db_session.add(InteracaoTenant(tenant_id=TENANT_ID, tipo="reclamacao", criado_em=_agora_menos_dias(45)))
    db_session.commit()

    resultado = motor_service.calcular_score_risco(db_session, TENANT_ID)

    assert "reclamacoes" not in resultado["sinais"]
    assert resultado["score"] == 10.0


def test_score_risco_mencao_concorrente_e_reuniao_remarcada_somam(db_session):
    _criar_tenant(db_session)
    db_session.add(InteracaoTenant(tenant_id=TENANT_ID, tipo="contato", criado_em=_agora_menos_dias(1)))
    db_session.add(InteracaoTenant(tenant_id=TENANT_ID, tipo="mencionou_concorrente", criado_em=_agora_menos_dias(2)))
    db_session.add(InteracaoTenant(tenant_id=TENANT_ID, tipo="reuniao_remarcada", criado_em=_agora_menos_dias(3)))
    db_session.commit()

    resultado = motor_service.calcular_score_risco(db_session, TENANT_ID)

    assert resultado["sinais"]["mencionou_concorrente"] == 20
    assert resultado["sinais"]["reuniao_remarcada"] == 15
    assert resultado["score"] == 45.0  # base 10 + 20 + 15
    assert resultado["classificacao"] == "atencao"


def test_score_risco_feedback_positivo_reduz_e_conta_como_contato(db_session):
    _criar_tenant(db_session)
    for _ in range(5):
        db_session.add(InteracaoTenant(tenant_id=TENANT_ID, tipo="reclamacao", criado_em=_agora_menos_dias(20)))
    db_session.add(InteracaoTenant(tenant_id=TENANT_ID, tipo="feedback_positivo", criado_em=_agora_menos_dias(1)))
    db_session.commit()

    resultado = motor_service.calcular_score_risco(db_session, TENANT_ID)

    assert resultado["dias_sem_contato"] < 7  # feedback_positivo conta como contato
    assert resultado["sinais"]["feedback_positivo"] == -20
    assert resultado["score"] == 35.0  # base 10 + reclamacoes 45 - feedback 20
    assert resultado["classificacao"] == "saudavel"


def test_score_risco_nunca_fica_negativo(db_session):
    _criar_tenant(db_session)
    db_session.add(InteracaoTenant(tenant_id=TENANT_ID, tipo="feedback_positivo", criado_em=_agora_menos_dias(1)))
    db_session.commit()

    resultado = motor_service.calcular_score_risco(db_session, TENANT_ID)

    assert resultado["score"] == 0.0


def test_ranking_saude_tenants_cross_tenant_com_valor_em_risco(db_session):
    _criar_tenant(db_session, "tenant-saudavel", preco_mensal=300.0)
    _criar_tenant(db_session, "tenant-critico", preco_mensal=1000.0)
    licenca_critico = db_session.query(Licenca).filter_by(tenant_id="tenant-critico").one()
    licenca_critico.data_inicio = _agora_menos_dias(90)
    for _ in range(5):
        db_session.add(InteracaoTenant(tenant_id="tenant-critico", tipo="reclamacao", criado_em=_agora_menos_dias(2)))
    db_session.add(InteracaoTenant(tenant_id="tenant-critico", tipo="mencionou_concorrente", criado_em=_agora_menos_dias(2)))
    db_session.commit()

    ranking = motor_service.ranking_saude_tenants(db_session)

    assert ranking[0]["tenant_id"] == "tenant-critico"
    assert ranking[0]["classificacao"] == "critico"
    assert ranking[0]["valor_em_risco"] == pytest.approx(1000.0 * 3.0, rel=0.05)

    entrada_saudavel = next(item for item in ranking if item["tenant_id"] == "tenant-saudavel")
    assert entrada_saudavel["classificacao"] == "saudavel"
    assert entrada_saudavel["valor_em_risco"] == 0.0


def test_dashboard_motor_agrega_ranking(db_session):
    _criar_tenant(db_session, "tenant-a", preco_mensal=200.0)
    _criar_tenant(db_session, "tenant-b", preco_mensal=400.0)

    dashboard = motor_service.dashboard_motor(db_session)

    assert dashboard["total_tenants"] == 2
    assert dashboard["saudaveis"] == 2
    assert dashboard["criticos"] == 0
    assert dashboard["valor_total_em_risco"] == 0.0
    assert dashboard["score_medio"] == 10.0


def test_dashboard_motor_sem_tenants_retorna_score_medio_none(db_session):
    dashboard = motor_service.dashboard_motor(db_session)

    assert dashboard["total_tenants"] == 0
    assert dashboard["score_medio"] is None


def test_gerar_script_resgate_usa_llm_provider(db_session):
    from tests.fakes import FakeLLMProvider

    _criar_tenant(db_session)
    motor_service.registrar_interacao(db_session, TENANT_ID, ATOR_ID, "reclamacao", "Suporte demorado")
    llm = FakeLLMProvider()
    llm.definir_respostas(["Olá, vimos que você teve uma experiência ruim recentemente..."])

    resultado = motor_service.gerar_script_resgate(db_session, TENANT_ID, llm)

    assert resultado["tenant_id"] == TENANT_ID
    assert resultado["script"] == "Olá, vimos que você teve uma experiência ruim recentemente..."
    assert len(llm.chamadas) == 1
