from datetime import UTC, datetime, timedelta

from app.models.atividade import Atividade
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.services import conta_service, crm_service, sinal_oportunidade_service

TENANT_A = "tenant-teste"


def _criar_negocio(db_session, tenant_id=TENANT_A, cargo_decisor: str | None = None) -> tuple:
    conta = Conta(tenant_id=tenant_id, nome="Conta Teste", status="priorizada")
    db_session.add(conta)
    db_session.flush()
    decisor = Decisor(tenant_id=tenant_id, conta_id=conta.id, nome="Decisor Teste", cargo=cargo_decisor)
    db_session.add(decisor)
    db_session.commit()

    negocio = crm_service.criar_negocio(db_session, tenant_id, None, conta.id, decisor.id, "Negócio Teste", valor=1000)
    return conta, decisor, negocio


def test_negocio_recente_sem_atividade_nenhuma_nao_gera_risco_de_parado(db_session):
    conta, decisor, negocio = _criar_negocio(db_session)
    conta_service.confirmar_papel_decisor(db_session, TENANT_A, None, conta.id, decisor.id, "DECISION_MAKER")
    conta.proximo_passo = "Ligar semana que vem"
    db_session.commit()

    resultado = sinal_oportunidade_service.analisar_pipeline(db_session, TENANT_A, negocio)

    assert not any("parado" in risco.lower() for risco in resultado["riscos"])


def test_negocio_parado_sem_atividade_gera_risco(db_session):
    conta, decisor, negocio = _criar_negocio(db_session)
    negocio.criado_em = datetime.now(UTC) - timedelta(days=20)
    # `criar_negocio` já registra uma Atividade "sistema" na criação —
    # pra testar "parado" de verdade, ela também precisa ser antiga.
    db_session.query(Atividade).filter_by(negocio_id=negocio.id).update({"criado_em": negocio.criado_em})
    db_session.commit()

    resultado = sinal_oportunidade_service.analisar_pipeline(db_session, TENANT_A, negocio)

    assert resultado["dias_sem_atividade"] == 20
    assert any("parado" in risco.lower() for risco in resultado["riscos"])


def test_negocio_com_atividade_recente_nao_gera_risco_de_parado(db_session):
    conta, decisor, negocio = _criar_negocio(db_session)
    negocio.criado_em = datetime.now(UTC) - timedelta(days=20)
    db_session.commit()
    atividade = Atividade(tenant_id=TENANT_A, conta_id=conta.id, negocio_id=negocio.id, tipo="nota", descricao="Contato recente")
    db_session.add(atividade)
    db_session.commit()

    resultado = sinal_oportunidade_service.analisar_pipeline(db_session, TENANT_A, negocio)

    assert resultado["dias_sem_atividade"] == 0
    assert not any("parado" in risco.lower() for risco in resultado["riscos"])


def test_sem_decision_maker_confirmado_gera_risco(db_session):
    conta, decisor, negocio = _criar_negocio(db_session)

    resultado = sinal_oportunidade_service.analisar_pipeline(db_session, TENANT_A, negocio)

    assert resultado["tem_decision_maker"] is False
    assert any("decision_maker" in risco.lower() or "decisor" in risco.lower() for risco in resultado["riscos"])


def test_com_decision_maker_confirmado_nao_gera_esse_risco(db_session):
    conta, decisor, negocio = _criar_negocio(db_session)
    conta_service.confirmar_papel_decisor(db_session, TENANT_A, None, conta.id, decisor.id, "DECISION_MAKER")

    resultado = sinal_oportunidade_service.analisar_pipeline(db_session, TENANT_A, negocio)

    assert resultado["tem_decision_maker"] is True


def test_sem_proximo_passo_gera_risco(db_session):
    conta, decisor, negocio = _criar_negocio(db_session)

    resultado = sinal_oportunidade_service.analisar_pipeline(db_session, TENANT_A, negocio)

    assert any("próximo passo" in risco.lower() for risco in resultado["riscos"])


def test_proximo_passo_atrasado_gera_risco(db_session):
    conta, decisor, negocio = _criar_negocio(db_session)
    conta.proximo_passo = "Enviar proposta"
    conta.proximo_passo_em = datetime.now(UTC) - timedelta(days=3)
    db_session.commit()

    resultado = sinal_oportunidade_service.analisar_pipeline(db_session, TENANT_A, negocio)

    assert any("atrasado" in risco.lower() for risco in resultado["riscos"])


def test_listar_riscos_pipeline_so_negocios_abertos_com_risco(db_session):
    conta, decisor, negocio_com_risco = _criar_negocio(db_session)

    conta2 = Conta(tenant_id=TENANT_A, nome="Conta Sem Risco", status="priorizada")
    db_session.add(conta2)
    db_session.flush()
    decisor2 = Decisor(tenant_id=TENANT_A, conta_id=conta2.id, nome="Decisor 2")
    db_session.add(decisor2)
    db_session.commit()
    negocio_sem_risco = crm_service.criar_negocio(db_session, TENANT_A, None, conta2.id, decisor2.id, "Negócio Sem Risco")
    conta_service.confirmar_papel_decisor(db_session, TENANT_A, None, conta2.id, decisor2.id, "DECISION_MAKER")
    conta2.proximo_passo = "Follow-up agendado"
    db_session.add(Atividade(tenant_id=TENANT_A, conta_id=conta2.id, negocio_id=negocio_sem_risco.id, tipo="nota", descricao="ok"))
    db_session.commit()

    resultados = sinal_oportunidade_service.listar_riscos_pipeline(db_session, TENANT_A)

    ids_com_risco = {resultado["negocio_id"] for resultado in resultados}
    assert negocio_com_risco.id in ids_com_risco
    assert negocio_sem_risco.id not in ids_com_risco


def test_listar_riscos_pipeline_isolamento_tenant(db_session):
    _criar_negocio(db_session, tenant_id=TENANT_A)
    _criar_negocio(db_session, tenant_id="tenant-outro")

    resultados = sinal_oportunidade_service.listar_riscos_pipeline(db_session, TENANT_A)

    assert all(resultado["conta_id"] for resultado in resultados)
    resultados_outro = sinal_oportunidade_service.listar_riscos_pipeline(db_session, "tenant-outro")
    assert len(resultados) == 1
    assert len(resultados_outro) == 1
