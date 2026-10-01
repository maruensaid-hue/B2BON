"""D-078: CBS/IBS de 2026 — alíquotas-teste preservadas (CBS 0,90%, IBS 0,10%), imposto de caixa pela situação do período
(TaxStatusPeriod): WAIVED_BY_COMPLIANCE = zero, COMPENSATED sem dupla contagem com PIS/COFINS, PAYABLE recolhido."""

import importlib.util
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.contexts.comissoes import contract as comissoes
from app.models.apuracao_comissao import ApuracaoComissao
from app.models.auditoria import AuditLog
from app.services.errors import ValidacaoFalhou
from tests.integration.test_comissao_margem import _comissoes, _receber, professional  # noqa: F401
from tests.parametros_comissao import componente

RAIZ = Path(__file__).resolve().parents[2]


def _mig(arquivo):
    spec = importlib.util.spec_from_file_location(arquivo, RAIZ / "alembic/versions" / arquivo)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


MIG = _mig("d0f2b4c6e8a1_status_cbs_ibs_2026.py")
MIG_D076 = _mig("b7d9f1a3c5e8_pool_infraestrutura_tributos_2026.py")
HOJE = date.today()
PERFIL = [{"tributo": "PIS", "base": "RECEITA", "aliquota": 0.0065}, {"tributo": "COFINS", "base": "RECEITA", "aliquota": 0.03},
          MIG_D076._cbs_ibs("CBS", 0.009), MIG_D076._cbs_ibs("IBS", 0.001)]


def _parametros(db):
    comissoes.tributos.criar(db, {"regime": "LUCRO_PRESUMIDO", "vigente_de": date(2000, 1, 1), "componentes": PERFIL}, "teste")
    comissoes.infraestrutura.criar(db, componente(0.0), "teste")
    db.commit()


def _periodo(db, status, inicio=HOJE - timedelta(days=30), fim=HOJE + timedelta(days=30)):
    periodo = comissoes.tributos.criar_status_periodo(db, {"status": status, "vigente_de": inicio, "vigente_ate": fim, "motivo": "teste",
                                                           "aprovado_por": "Contabilidade"}, "teste")
    db.commit()
    return periodo


def _apuracao(db, recebimento):
    return db.query(ApuracaoComissao).filter_by(recebimento_governo_id=recebimento.id).one()


def _reforma(apuracao):
    return apuracao.detalhe["tributos"]["reforma"]


def test_configuracao_2026_aprovada_e_aliquotas_teste_preservadas():
    assert (MIG.PERIODO_2026["status"], MIG.PERIODO_2026["vigente_de"], MIG.PERIODO_2026["vigente_ate"]) == (
        "WAIVED_BY_COMPLIANCE", date(2026, 1, 1), date(2026, 12, 31))
    assert "EC 132/2023" in MIG.REFERENCIA_LEGAL and "LC 214/2025" in MIG.REFERENCIA_LEGAL
    for _, _, _, presuncao, iss, _ in MIG_D076.PERFIS:
        taxas = {c["tributo"]: c.get("aliquota_teste") for c in MIG_D076.componentes(presuncao, iss) if c["base"] == "TESTE_REFORMA"}
        assert taxas == {"CBS": 0.009, "IBS": 0.001}  # nunca apagadas


def test_dispensa_por_conformidade_caixa_zero_e_margem_intacta(db_session, professional):  # noqa: F811
    _parametros(db_session)
    _periodo(db_session, "WAIVED_BY_COMPLIANCE")
    apuracao = _apuracao(db_session, _receber(db_session, professional, "LICENSE", 100_000))
    reforma = _reforma(apuracao)
    assert (reforma["cbs_test_rate"], reforma["ibs_test_rate"]) == (0.009, 0.001)
    assert (reforma["cbs_nominal_test_tax"], reforma["ibs_nominal_test_tax"]) == (900.0, 100.0)  # NOMINAL_TEST_TAX
    assert (reforma["cbs_cash_tax"], reforma["ibs_cash_tax"], reforma["status"]) == (0.0, 0.0, "WAIVED_BY_COMPLIANCE")
    assert apuracao.impostos == Decimal("3650.00")  # só PIS 650 + COFINS 3.000; CBS/IBS não reduzem a margem
    assert apuracao.margem_comissionavel_liquida == Decimal("96350.00") and _comissoes(db_session)[0].valor_comissao == 19_270.0


def test_compensado_sem_dupla_contagem_com_pis_cofins(db_session, professional):  # noqa: F811
    _parametros(db_session)
    _periodo(db_session, "COMPENSATED")
    apuracao = _apuracao(db_session, _receber(db_session, professional, "LICENSE", 100_000))
    reforma = _reforma(apuracao)
    assert (reforma["cbs_ibs_paid"], reforma["pis_cofins_offset"], reforma["net_tax_effect"]) == (1000.0, 1000.0, 0.0)
    assert apuracao.impostos == Decimal("3650.00")  # nunca 4.650 (CBS/IBS + PIS/COFINS integrais)


def test_devido_por_nao_conformidade_continua_suportado(db_session, professional):  # noqa: F811
    _parametros(db_session)
    _periodo(db_session, "PAYABLE")
    apuracao = _apuracao(db_session, _receber(db_session, professional, "LICENSE", 100_000))
    assert (_reforma(apuracao)["cbs_cash_tax"], _reforma(apuracao)["ibs_cash_tax"], apuracao.impostos) == (900.0, 100.0, Decimal("4650.00"))


def test_mudanca_de_situacao_tem_vigencia_e_nao_altera_comissao_paga(client, db_session, professional):  # noqa: F811
    _parametros(db_session)
    _periodo(db_session, "WAIVED_BY_COMPLIANCE")
    primeira = _apuracao(db_session, _receber(db_session, professional, "LICENSE", 60_000, HOJE - timedelta(days=20)))
    paga = _comissoes(db_session)[0]
    paga.status = "PAID"
    db_session.commit()
    resposta = client.post("/api/v1/comissoes/status-tributario", json={
        "status": "PAYABLE", "vigente_de": (HOJE - timedelta(days=10)).isoformat(), "motivo": "Obrigação acessória não entregue",
        "aprovado_por": "Contabilidade", "referencia_evidencia": "Parecer contábil 01"})
    assert resposta.status_code == 201
    anterior = comissoes.tributos.status_vigente(db_session, HOJE - timedelta(days=20))
    assert (anterior.status, anterior.vigente_ate) == ("WAIVED_BY_COMPLIANCE", HOJE - timedelta(days=11))  # nova vigência, sem reescrever
    comissoes.motor.recalcular_nao_pagas(db_session, "Mudança de situação", "teste")
    db_session.refresh(paga)
    db_session.refresh(primeira)
    assert (paga.valor_comissao, primeira.impostos, _reforma(primeira)["status"]) == (11_562.0, Decimal("2190.00"), "WAIVED_BY_COMPLIANCE")
    segunda = _apuracao(db_session, _receber(db_session, professional, "LICENSE", 40_000))
    assert (_reforma(segunda)["status"], segunda.impostos) == ("PAYABLE", Decimal("1860.00"))  # 260 + 1.200 + 360 + 40
    log = db_session.query(AuditLog).filter_by(evento_tipo="status_tributario_alterado").order_by(AuditLog.id.desc()).first()
    assert log.detalhes["aprovado_por"] == "Contabilidade" and log.detalhes["evidencia"] == "Parecer contábil 01"
    with pytest.raises(ValidacaoFalhou, match="histórico"):
        _periodo(db_session, "COMPENSATED", inicio=HOJE - timedelta(days=10))
    with pytest.raises(ValidacaoFalhou, match="aprovou"):
        comissoes.tributos.criar_status_periodo(db_session, {"status": "PAYABLE", "vigente_de": HOJE + timedelta(days=90), "motivo": "x",
                                                             "aprovado_por": ""}, "teste")


def test_snapshot_tributario_e_map(client, db_session, professional):  # noqa: F811
    _parametros(db_session)
    _periodo(db_session, "WAIVED_BY_COMPLIANCE")
    _receber(db_session, professional, "LICENSE", 100_000)
    snapshot = client.get("/api/v1/comissoes/apuracoes").json()[0]["tax_snapshot"]
    assert {k: snapshot[k] for k in ("cbs_test_rate", "ibs_test_rate", "cbs_ibs_status", "cbs_cash_tax", "ibs_cash_tax",
                                     "pis_cofins_offset", "total_attributable_tax")} == {
        "cbs_test_rate": 0.009, "ibs_test_rate": 0.001, "cbs_ibs_status": "WAIVED_BY_COMPLIANCE", "cbs_cash_tax": 0.0, "ibs_cash_tax": 0.0,
        "pis_cofins_offset": 0.0, "total_attributable_tax": 3650.0}
    assert snapshot["tax_profile_id"] and snapshot["calculated_at"]
    reforma = client.get("/api/v1/comissoes/waterfall").json()["total"]["reforma_tributaria"]
    assert (reforma["cbs_test_rate"], reforma["ibs_test_rate"], reforma["cbs_cash_tax"], reforma["ibs_cash_tax"]) == (0.009, 0.001, 0.0, 0.0)
    assert reforma["status_rotulo"] == "Dispensado de recolhimento mediante conformidade"
    assert client.get("/api/v1/comissoes/parametros").json()["status_tributario_vigente"]["status"] == "WAIVED_BY_COMPLIANCE"
