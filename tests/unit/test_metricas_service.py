from datetime import UTC, datetime, timedelta

from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.pesquisa_nps import PesquisaNps
from app.services import conta_service, crm_service, metricas_service

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


def _criar_negocio_fechado(
    db_session, tipo_estagio: str, valor: float = 1000.0, motivo_perda: str | None = None,
    decision_maker: bool = False, dias_para_fechar: int = 10,
):
    conta = Conta(tenant_id=TENANT_ID, nome="Conta Teste", status="priorizada")
    db_session.add(conta)
    db_session.flush()
    decisor = Decisor(tenant_id=TENANT_ID, conta_id=conta.id, nome="Decisor Teste")
    db_session.add(decisor)
    db_session.commit()

    negocio = crm_service.criar_negocio(db_session, TENANT_ID, None, conta.id, decisor.id, "Negócio Teste", valor=valor)
    negocio.criado_em = datetime.now(UTC) - timedelta(days=dias_para_fechar)
    db_session.commit()

    estagio_alvo = next(e for e in crm_service.garantir_estagios_padrao(db_session, TENANT_ID) if e.tipo == tipo_estagio)
    crm_service.mover_estagio(db_session, TENANT_ID, None, negocio.id, estagio_alvo.id, motivo_perda=motivo_perda)
    db_session.refresh(negocio)

    if decision_maker:
        conta_service.confirmar_papel_decisor(db_session, TENANT_ID, None, conta.id, decisor.id, "DECISION_MAKER")

    return conta, decisor, negocio


def test_padroes_observados_sem_dados_retorna_tudo_none(db_session):
    resultado = metricas_service.calcular_padroes_observados(db_session, TENANT_ID)

    assert resultado["ticket_medio"] is None
    assert resultado["ciclo_medio_dias"] is None
    assert resultado["motivo_perda_mais_comum"] is None
    assert resultado["taxa_ganho_com_decision_maker"] is None


def test_padroes_observados_amostra_insuficiente_fica_none(db_session):
    _criar_negocio_fechado(db_session, "ganho", valor=1000.0)
    _criar_negocio_fechado(db_session, "ganho", valor=2000.0)

    resultado = metricas_service.calcular_padroes_observados(db_session, TENANT_ID)

    assert resultado["amostra_ticket_medio"] == 2
    assert resultado["ticket_medio"] is None  # amostra < 3


def test_padroes_observados_ticket_e_ciclo_medio_com_amostra_suficiente(db_session):
    _criar_negocio_fechado(db_session, "ganho", valor=1000.0, dias_para_fechar=10)
    _criar_negocio_fechado(db_session, "ganho", valor=2000.0, dias_para_fechar=20)
    _criar_negocio_fechado(db_session, "ganho", valor=3000.0, dias_para_fechar=30)

    resultado = metricas_service.calcular_padroes_observados(db_session, TENANT_ID)

    assert resultado["amostra_ticket_medio"] == 3
    assert resultado["ticket_medio"] == 2000.0
    assert resultado["amostra_ciclo_medio"] == 3
    assert resultado["ciclo_medio_dias"] == 20.0


def test_padroes_observados_motivo_perda_mais_comum(db_session):
    _criar_negocio_fechado(db_session, "perdido", motivo_perda="Preço/orçamento")
    _criar_negocio_fechado(db_session, "perdido", motivo_perda="Preço/orçamento")
    _criar_negocio_fechado(db_session, "perdido", motivo_perda="Escolheu concorrente")

    resultado = metricas_service.calcular_padroes_observados(db_session, TENANT_ID)

    assert resultado["motivo_perda_mais_comum"] == "Preço/orçamento"
    assert resultado["motivo_perda_mais_comum_contagem"] == 2


def test_padroes_observados_taxa_ganho_com_decision_maker(db_session):
    _criar_negocio_fechado(db_session, "ganho", decision_maker=True)
    _criar_negocio_fechado(db_session, "ganho", decision_maker=True)
    _criar_negocio_fechado(db_session, "perdido", motivo_perda="Preço/orçamento", decision_maker=False)

    resultado = metricas_service.calcular_padroes_observados(db_session, TENANT_ID)

    assert resultado["amostra_decision_maker"] == 3
    assert resultado["taxa_ganho_com_decision_maker"] == 1.0
    assert resultado["taxa_ganho_sem_decision_maker"] == 0.0


def test_padroes_observados_isolamento_tenant(db_session):
    _criar_negocio_fechado(db_session, "ganho", valor=1000.0)
    _criar_negocio_fechado(db_session, "ganho", valor=2000.0)
    _criar_negocio_fechado(db_session, "ganho", valor=3000.0)

    resultado = metricas_service.calcular_padroes_observados(db_session, "tenant-outro")

    assert resultado["amostra_ticket_medio"] == 0
