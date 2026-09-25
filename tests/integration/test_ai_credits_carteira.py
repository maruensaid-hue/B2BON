"""AI Credits — carteira, extrato, reservas e idempotência (Fase 15)."""

from datetime import timedelta
from decimal import Decimal

import pytest

from app.contexts.finops import carteira, catalogos, execucoes
from app.contexts.finops.comercial import TipoLote
from app.core.config import settings
from app.models.carteira_creditos import MovimentoCredito
from app.models.creditos_ia import ExecucaoIa, LoteCreditos
from app.models.licenca import Licenca
from app.models.plano import Plano
from app.models.tenant import Tenant
from app.services.errors import ConfirmacaoNecessaria, CreditosInsuficientes

A, B = "tenant-carteira-a", "tenant-carteira-b"
pytestmark = pytest.mark.usefixtures("cobranca_ativa")


@pytest.fixture()
def tenants(db_session):
    for tenant_id in (A, B):
        db_session.add(Tenant(id=tenant_id, razao_social=tenant_id))
    db_session.commit()
    return A, B


def _conceder(db, tenant, quantidade, tipo=TipoLote.TOPUP, dias=None, chave=None, receita="0.02"):
    lote = carteira.conceder(db, tenant, tipo, quantidade, "teste", idempotency_key=chave,
                             expira_em=carteira.agora_utc() + timedelta(days=dias) if dias is not None else None,
                             receita_por_credito=Decimal(receita))
    db.commit()
    return lote


def _disponivel(db, tenant):
    db.expire_all()
    return carteira.disponivel(db, tenant)


def test_catalogos_semeados_com_os_valores_do_po(db_session):
    pacotes = {p.codigo: catalogos.pacote_dict(p) for p in catalogos.pacotes_vigentes(db_session)}
    assert [(p["creditos"], p["preco"]) for p in pacotes.values()] == [
        (5000, 99.0), (15000, 249.0), (30000, 449.0), (75000, 899.0), (150000, 1499.0), (350000, 2999.0), (1000000, 6990.0), (None, None)]
    assert [pacotes[c]["preco_efetivo_por_1000"] for c in ("AI_START", "AI_15K", "AI_30K", "AI_75K", "AI_150K", "AI_350K", "AI_1M")] == [
        19.8, 16.6, 14.97, 11.99, 9.99, 8.57, 6.99]
    assert pacotes["ENTERPRISE"]["status"] == "CONTACT_SALES"
    pesos = {w.codigo: float(w.creditos_base) for w in catalogos.workloads(db_session)}
    assert (pesos["classification_simple"], pesos["cadence_generation"], pesos["opportunity_intelligence"], pesos["tender_analysis"],
            pesos["full_go_no_go"], pesos["procurement_deterministic"]) == (1, 8, 15, 50, 100, 0)
    assert catalogos.catalogo_ativo(db_session).versao == "CREDIT_CATALOG_V1"


def test_estimativa_variavel_respeita_minimo_e_maximo(db_session):
    catalogo = catalogos.catalogo_ativo(db_session)
    complexo = catalogos.obter_workload(db_session, "complex_multi_document_analysis")
    assert catalogos.estimar(complexo, catalogo.versao, {}).creditos == 150
    assert catalogos.estimar(complexo, catalogo.versao, {"documentos": 3, "paginas": 40}).creditos == 220
    assert catalogos.estimar(complexo, catalogo.versao, {"documentos": 10, "paginas": 800, "ocr": True}).creditos == 300
    documento = catalogos.obter_workload(db_session, "procurement_document_intelligence")
    assert catalogos.estimar(documento, catalogo.versao, {"paginas": 200}).creditos == 225


def test_concessao_idempotente_e_fefo(db_session, tenants):
    _conceder(db_session, A, 100, dias=None, chave="k1")
    _conceder(db_session, A, 100, dias=None, chave="k1")  # mesma chave: não duplica
    _conceder(db_session, A, 50, dias=5, tipo=TipoLote.SUBSCRIPTION)
    _conceder(db_session, A, 30, dias=2, tipo=TipoLote.PROMOTIONAL)
    assert _disponivel(db_session, A) == 180
    ordem = [(lote.tipo, float(lote.quantidade_restante)) for lote in carteira.lotes_fefo(db_session, A)]
    assert ordem == [("PROMOTIONAL", 30), ("SUBSCRIPTION", 50), ("TOPUP", 100)]  # vence antes, sai antes


def test_reserva_liquidacao_consome_fefo_e_calcula_receita(db_session, tenants):
    _conceder(db_session, A, 5, dias=1, tipo=TipoLote.PROMOTIONAL, receita="0")
    _conceder(db_session, A, 100, receita="0.0198")
    execucao = execucoes.abrir(db_session, A, "cadence_generation")  # 8 créditos
    assert (execucao.status, float(execucao.creditos_reservados)) == ("RESERVADA", 8)
    assert _disponivel(db_session, A) == 97
    liquidada = execucoes.liquidar(db_session, execucao.id)
    assert (liquidada.status, float(liquidada.creditos_liquidados)) == ("LIQUIDADA", 8)
    assert float(liquidada.receita_brl) == pytest.approx(3 * 0.0198)  # 5 promocionais (sem receita) + 3 pagos
    assert _disponivel(db_session, A) == 97
    consumos = db_session.query(MovimentoCredito).filter_by(execucao_id=execucao.id, tipo="CREDIT_CONSUMED").all()
    assert sorted(-float(m.quantidade) for m in consumos) == [3, 5]
    assert carteira.reconciliar(db_session, A)["consistente"]


def test_critico_retry_com_mesma_execucao_cobra_uma_vez(db_session, tenants):
    _conceder(db_session, A, 100)
    primeira = execucoes.abrir(db_session, A, "opportunity_intelligence", idempotency_key="exec-1")
    execucoes.liquidar(db_session, primeira.id)
    retry = execucoes.abrir(db_session, A, "opportunity_intelligence", idempotency_key="exec-1")
    execucoes.liquidar(db_session, retry.id)
    execucoes.liquidar(db_session, primeira.id)
    assert retry.id == primeira.id
    assert db_session.query(ExecucaoIa).filter_by(tenant_id=A).count() == 1
    assert _disponivel(db_session, A) == 85  # 15 uma única vez
    assert db_session.query(MovimentoCredito).filter_by(execucao_id=primeira.id, tipo="CREDIT_CONSUMED").count() == 1


def test_critico_saldo_100_duas_operacoes_de_80(db_session, tenants):
    _conceder(db_session, A, 100)
    primeira = execucoes.abrir(db_session, A, "tender_terms_of_reference")  # 75
    with pytest.raises(CreditosInsuficientes):
        execucoes.abrir(db_session, A, "tender_terms_of_reference")  # a reserva da primeira já prende o saldo
    execucoes.liquidar(db_session, primeira.id)
    assert _disponivel(db_session, A) == 25
    total_liquidado = sum(float(e.creditos_liquidados) for e in db_session.query(ExecucaoIa).filter_by(tenant_id=A))
    assert total_liquidado == 75


def test_critico_tenant_b_nao_usa_saldo_de_a(db_session, tenants):
    _conceder(db_session, A, 10_000)
    with pytest.raises(CreditosInsuficientes):
        execucoes.abrir(db_session, B, "tender_analysis")
    assert _disponivel(db_session, A) == 10_000
    assert carteira.lotes_fefo(db_session, B) == []


def test_falha_libera_reserva_e_estorno_devolve_consumo(db_session, tenants):
    _conceder(db_session, A, 100)
    with pytest.raises(RuntimeError):
        with execucoes.executar(db_session, A, "tender_analysis"):
            assert _disponivel(db_session, A) == 50
            raise RuntimeError("provedor fora do ar")
    assert _disponivel(db_session, A) == 100
    assert db_session.query(ExecucaoIa).filter_by(tenant_id=A).one().status == "LIBERADA"

    with execucoes.executar(db_session, A, "tender_analysis") as execucao:
        pass
    assert _disponivel(db_session, A) == 50
    execucoes.estornar(db_session, execucao.id, "resultado inutilizável")
    assert _disponivel(db_session, A) == 100
    assert db_session.get(ExecucaoIa, execucao.id).status == "ESTORNADA"
    assert db_session.query(MovimentoCredito).filter_by(execucao_id=execucao.id, tipo="CREDIT_REFUNDED").count() == 1
    assert carteira.reconciliar(db_session, A)["consistente"]


def test_expiracao_gera_evento_e_nao_afeta_outros_lotes(db_session, tenants):
    _conceder(db_session, A, 40, dias=10)
    lote = _conceder(db_session, A, 60, dias=10, tipo=TipoLote.SUBSCRIPTION)
    lote.expira_em = carteira.agora_utc() - timedelta(minutes=1)
    db_session.commit()
    assert carteira.expirar_vencidos(db_session, A) == 60
    db_session.commit()
    assert _disponivel(db_session, A) == 40
    assert db_session.query(MovimentoCredito).filter_by(tenant_id=A, tipo="CREDIT_EXPIRED").one().quantidade == -60
    assert db_session.get(LoteCreditos, lote.id).status == "EXPIRADO"
    assert carteira.reconciliar(db_session, A)["consistente"]


def test_confirmacao_para_operacao_cara(db_session, tenants):
    _conceder(db_session, A, 1000)
    with pytest.raises(ConfirmacaoNecessaria) as erro:
        execucoes.abrir(db_session, A, "procurement_document_intelligence", parametros={"paginas": 200})
    assert erro.value.detalhe["creditos_estimados"] == 225
    assert "aproximadamente 225 AI Credits" in str(erro.value)
    execucao = execucoes.abrir(db_session, A, "procurement_document_intelligence", parametros={"paginas": 200}, confirmado=True)
    assert float(execucao.creditos_reservados) == 225


def test_franquia_mensal_pelo_plano_sem_rollover(db_session, tenants):
    plano = Plano(nome="Suíte", franquia_contas_mes=1, preco_mensal=10, modulos_contratados=["crm", "map", "predator", "procurement"])
    db_session.add(plano)
    db_session.flush()
    db_session.add(Licenca(tenant_id=A, plano_id=plano.id, status="ativa"))
    db_session.commit()
    carteira.preparar(db_session, A)
    carteira.preparar(db_session, A)
    db_session.commit()
    lotes = db_session.query(LoteCreditos).filter_by(tenant_id=A, tipo="SUBSCRIPTION").all()
    assert len(lotes) == 1 and float(lotes[0].quantidade_original) == 35_000  # procurement: franquia pendente não soma
    assert lotes[0].expira_em.day == 1 and lotes[0].expira_em > carteira.agora_utc()


def test_modo_measure_nao_bloqueia_e_registra_excedente_nao_faturavel(db_session, tenants, monkeypatch):
    monkeypatch.setattr(settings, "ai_creditos_modo", "MEASURE")
    execucao = execucoes.abrir(db_session, A, "short_summary")
    liquidada = execucoes.liquidar(db_session, execucao.id)
    assert float(liquidada.creditos_excedente) == 1
    excedente = db_session.query(MovimentoCredito).filter_by(execucao_id=execucao.id, tipo="CREDIT_OVERAGE").one()
    assert excedente.faturavel is False
