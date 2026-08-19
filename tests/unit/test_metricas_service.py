from datetime import UTC, datetime

from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.pesquisa_nps import PesquisaNps
from app.services import metricas_service

TENANT_ID = "tenant-teste"


def test_calcular_roi_com_ltv_e_cac():
    assert metricas_service.calcular_roi(ltv_medio=10000.0, cac=2000.0) == 5.0


def test_calcular_roi_sem_ltv_ou_cac_e_none():
    assert metricas_service.calcular_roi(ltv_medio=None, cac=2000.0) is None
    assert metricas_service.calcular_roi(ltv_medio=10000.0, cac=None) is None
    assert metricas_service.calcular_roi(ltv_medio=10000.0, cac=0.0) is None


def _criar_conta_com_decisor(db_session, nome: str) -> tuple[Conta, Decisor]:
    conta = Conta(tenant_id=TENANT_ID, icp_id=None, nome=nome, status="prospectada")
    db_session.add(conta)
    db_session.flush()
    decisor = Decisor(tenant_id=TENANT_ID, conta_id=conta.id, nome="Decisor Teste", telefone="+5511999999999")
    db_session.add(decisor)
    db_session.commit()
    return conta, decisor


def _responder_nps(db_session, conta: Conta, decisor: Decisor, nota: int) -> None:
    db_session.add(
        PesquisaNps(
            tenant_id=TENANT_ID, conta_id=conta.id, decisor_id=decisor.id, marco="entrega_concluida",
            nota=nota, classificacao="promotor" if nota >= 9 else "detrator",
            respondida_em=datetime.now(UTC),
        )
    )
    db_session.commit()


def test_cs_score_mistura_nps_e_saude_quando_ambos_disponiveis(db_session):
    conta, decisor = _criar_conta_com_decisor(db_session, "Empresa A")
    _responder_nps(db_session, conta, decisor, nota=10)  # normaliza pra 100

    resultado = metricas_service.calcular_cs_score(
        db_session, TENANT_ID, conta_ids=[conta.id], scores_risco=[20.0]  # saude = 80
    )

    assert resultado["nps_medio"] == 10.0
    assert resultado["saude_media"] == 80.0
    assert resultado["cs_score"] == 90.0  # média de 100 e 80


def test_cs_score_so_com_saude_quando_sem_resposta_de_nps(db_session):
    conta, _decisor = _criar_conta_com_decisor(db_session, "Empresa B")

    resultado = metricas_service.calcular_cs_score(
        db_session, TENANT_ID, conta_ids=[conta.id], scores_risco=[10.0]  # saude = 90
    )

    assert resultado["nps_medio"] is None
    assert resultado["saude_media"] == 90.0
    assert resultado["cs_score"] == 90.0


def test_cs_score_sem_contas_e_none(db_session):
    resultado = metricas_service.calcular_cs_score(db_session, TENANT_ID, conta_ids=[], scores_risco=[])

    assert resultado == {"cs_score": None, "nps_medio": None, "saude_media": None}
