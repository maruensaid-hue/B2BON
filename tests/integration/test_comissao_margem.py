"""D-074: comissão sobre a Margem Comissionável Líquida = receita recebida − impostos atribuíveis − infraestrutura
atribuível (incluído o custo de IA, quando o modelo o aloca). Alíquotas e custos aqui são de teste."""

import importlib.util
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.contexts.comissoes import contract as comissoes
from app.contexts.governo import contract as governo
from app.models.apuracao_comissao import ApuracaoComissao
from app.models.comissao_representante import ComissaoRepresentante
from app.models.plano import Plano
from app.models.representante import Representante
from app.models.tenant import Tenant
from tests.parametros_comissao import definir_parametros

RAIZ = Path(__file__).resolve().parents[2]
TENANT = "orgao-margem"
HOJE = date.today()
INFRA_5 = [{"categoria": "cloud_cost", "metodo": "PERCENTAGE", "percentual": 0.05}]


def _mig():
    spec = importlib.util.spec_from_file_location("mig_gov", RAIZ / "alembic/versions/d9e1f3a5b7c9_b2bon_government.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture()
def professional(db_session):
    mig = _mig()
    nome, licenca, implantacao, assinatura, creditos, recomendado = mig.PLANOS[1]
    plano = Plano(nome=nome, franquia_contas_mes=0, preco_mensal=0.0, visivel_self_service=False, modulos_contratados=["procurement"],
                  categoria="governo", tipo_preco="CONTRACT", segmento="GOVERNMENT", modelo_cobranca=mig.MODELO, preco_licenca=licenca,
                  preco_implantacao=implantacao, preco_assinatura_anual=assinatura, creditos_ia_anuais=creditos, recomendado=recomendado)
    db_session.add_all([plano, Tenant(id=TENANT, razao_social="Órgão")])
    rep = Representante(nome="Rep", email="rep@margem.com", chave_pix="pix", percentual_comissao=0.2)
    db_session.add(rep)
    db_session.commit()
    contrato = governo.contratos.criar(db_session, tenant_id=TENANT, plano_id=plano.id, modelo=mig.MODELO, referencia_contrato="CT-M",
                                       entidade_governamental="Órgão", assinado_em=HOJE - timedelta(days=370), representante_id=rep.id)
    return contrato


def _comp(db, contrato, tipo):
    return next(c for c in governo.contratos.componentes(db, contrato) if c.tipo == tipo)


def _receber(db, contrato, tipo, valor, dia=HOJE):
    return governo.recebimentos.registrar(db, contrato.id, componente_id=_comp(db, contrato, tipo).id, valor=valor, recebido_em=dia)


def _comissoes(db, **filtro):
    return db.query(ComissaoRepresentante).filter_by(**filtro).order_by(ComissaoRepresentante.id).all()


def test_licenca_e_subscricao_inicial_20_da_margem_e_nao_do_bruto(db_session, professional):
    definir_parametros(db_session, impostos=0.15, infra=INFRA_5)
    _receber(db_session, professional, "LICENSE", 120_000)
    _receber(db_session, professional, "INITIAL_ANNUAL_SUBSCRIPTION", 36_000)
    valores = {c.componente_tipo: (c.base_calculo, c.taxa, c.valor_comissao, c.status) for c in _comissoes(db_session)}
    # 156.000 − 15% impostos − 5% infraestrutura = 124.800 de margem; × 20% = 24.960 (não 31.200 = 156.000 × 20%)
    assert valores == {"LICENSE": (96_000.0, 0.2, 19_200.0, "PAYABLE"), "INITIAL_ANNUAL_SUBSCRIPTION": (28_800.0, 0.2, 5_760.0, "PAYABLE")}
    assert sum(v[2] for v in valores.values()) != 156_000 * 0.2


def test_impostos_e_infraestrutura_descontados_antes_da_comissao(db_session, professional):
    definir_parametros(db_session, impostos=0.1133, infra=[{"categoria": "cloud_cost", "metodo": "PERCENTAGE", "percentual": 0.04},
                                                           {"categoria": "database_cost", "metodo": "FIXED", "valor": 100}])
    recebimento = _receber(db_session, professional, "LICENSE", 120_000)
    apuracao = db_session.query(ApuracaoComissao).filter_by(recebimento_governo_id=recebimento.id).one()
    assert (apuracao.impostos, apuracao.custo_infra) == (Decimal("13596.00"), Decimal("4900.00"))
    assert apuracao.margem_comissionavel_liquida == Decimal("101504.00")
    assert _comissoes(db_session)[0].valor_comissao == 20_300.8


def test_custo_de_ia_descontado_antes_da_comissao_quando_a_politica_manda_sem_contar_duas_vezes(db_session, professional, monkeypatch):
    infra = [{"categoria": "cloud_cost", "metodo": "PERCENTAGE", "percentual": 0.05},
             {"categoria": "allocated_ai_infrastructure_cost", "metodo": "USAGE_BASED", "janela_dias": 30}]
    definir_parametros(db_session, impostos=0.15, infra=infra)
    comissoes.politica.nova(db_session, {"deduzir_custo_ia": True}, "PO: IA entra na margem", "teste")
    monkeypatch.setattr(comissoes.infraestrutura, "custo_ia_brl", lambda db, tenant, inicio, fim: (Decimal("1200.00"), None))
    _receber(db_session, professional, "LICENSE", 40_000)
    primeira = db_session.query(ApuracaoComissao).order_by(ApuracaoComissao.id).all()[-1]
    assert (primeira.custo_ia, primeira.custo_infra, primeira.margem_comissionavel_liquida) == (
        Decimal("1200.00"), Decimal("3200.00"), Decimal("30800.00"))  # 40.000 − 6.000 − (2.000 + 1.200)
    _receber(db_session, professional, "LICENSE", 40_000)  # mesmo dia: o custo de IA já atribuído não se repete
    segunda = db_session.query(ApuracaoComissao).order_by(ApuracaoComissao.id).all()[-1]
    assert segunda.custo_ia == 0 and segunda.margem_comissionavel_liquida == Decimal("32000.00")
    with pytest.raises(Exception, match="IA"):
        comissoes.infraestrutura.criar(db_session, {"nome": "x", "vigente_de": HOJE + timedelta(days=1), "componentes": [
            {"categoria": "allocated_ai_infrastructure_cost", "metodo": "USAGE_BASED"},
            {"categoria": "allocated_ai_infrastructure_cost", "metodo": "PERCENTAGE", "percentual": 0.01}]}, "teste")


def test_custo_de_ia_nao_entra_sem_a_politica_mesmo_existindo_no_finops(db_session, professional, monkeypatch):
    infra = [{"categoria": "cloud_cost", "metodo": "PERCENTAGE", "percentual": 0.05},
             {"categoria": "allocated_ai_infrastructure_cost", "metodo": "USAGE_BASED"}]
    definir_parametros(db_session, impostos=0.15, infra=infra)
    monkeypatch.setattr(comissoes.infraestrutura, "custo_ia_brl", lambda db, tenant, inicio, fim: (Decimal("1200.00"), None))
    _receber(db_session, professional, "LICENSE", 40_000)
    apuracao = db_session.query(ApuracaoComissao).one()
    assert (apuracao.custo_ia, apuracao.custo_infra, apuracao.margem_comissionavel_liquida) == (None, Decimal("2000.00"), Decimal("32000.00"))
    assert apuracao.detalhe["politica_margem"] == {"versao": 1, "deduzir_custo_ia": False}


def test_renovacao_10_da_margem_em_todas(db_session, professional):
    definir_parametros(db_session, impostos=0.15, infra=INFRA_5)
    for valor in (None, 37_800):
        periodo = governo.contratos.renovar(db_session, professional.id, valor_assinatura=valor,
                                            motivo_reajuste="Cláusula de reajuste" if valor else None)
        componente = next(c for c in governo.contratos.componentes(db_session, professional) if c.periodo_id == periodo.id)
        governo.recebimentos.registrar(db_session, professional.id, componente_id=componente.id, valor=componente.valor, recebido_em=HOJE)
    assert [(c.numero_renovacao, c.taxa, c.valor_comissao) for c in _comissoes(db_session)] == [(1, 0.1, 2_880.0), (2, 0.1, 3_024.0)]


def test_sem_tax_profile_aguarda_e_depois_calcula_sozinho(db_session, professional, client):
    comissoes.infraestrutura.criar(db_session, {"nome": "Infra", "vigente_de": date(2000, 1, 1), "componentes": INFRA_5}, "teste")
    db_session.commit()
    recebimento = _receber(db_session, professional, "LICENSE", 120_000)
    apuracao = db_session.query(ApuracaoComissao).filter_by(recebimento_governo_id=recebimento.id).one()
    comissao = _comissoes(db_session)[0]
    assert (apuracao.status, apuracao.parametros_faltantes) == ("AWAITING_COST_PARAMETERS", ["TAX_PROFILE"])
    assert (comissao.status, comissao.taxa, comissao.valor_comissao) == ("AWAITING_COST_PARAMETERS", 0.2, 0.0)
    resposta = client.post("/api/v1/comissoes/perfis-tributarios", json={
        "regime": "LUCRO_PRESUMIDO", "vigente_de": "2000-01-01",
        "componentes": [{"nome": "IRPJ", "aliquota": 0.05}, {"nome": "CSLL", "aliquota": 0.03}, {"nome": "PIS_COFINS", "aliquota": 0.07}]})
    assert resposta.status_code == 201 and resposta.json()["aguardando_calculadas"] == 1
    db_session.refresh(comissao)
    assert (comissao.status, comissao.valor_comissao) == ("PAYABLE", 19_200.0)


def test_sem_infraestrutura_aguarda(db_session, professional):
    comissoes.tributos.criar(db_session, {"regime": "LUCRO_PRESUMIDO", "vigente_de": date(2000, 1, 1),
                                          "componentes": [{"nome": "CARGA", "aliquota": 0.15}]}, "teste")
    db_session.commit()
    recebimento = _receber(db_session, professional, "LICENSE", 120_000)
    apuracao = db_session.query(ApuracaoComissao).filter_by(recebimento_governo_id=recebimento.id).one()
    assert (apuracao.status, apuracao.parametros_faltantes, apuracao.impostos) == ("AWAITING_COST_PARAMETERS", ["INFRASTRUCTURE_COST"],
                                                                                   Decimal("18000.00"))
    assert _comissoes(db_session)[0].status == "AWAITING_COST_PARAMETERS"


def test_implantacao_nao_comissiona_e_parcelas_sao_proporcionais(db_session, professional):
    definir_parametros(db_session, impostos=0.15, infra=INFRA_5)
    _receber(db_session, professional, "IMPLEMENTATION", 20_000)
    assert _comissoes(db_session) == []
    assert db_session.query(ApuracaoComissao).count() == 1  # apurada para o MAP mesmo sem comissão
    for _ in range(3):
        _receber(db_session, professional, "LICENSE", 40_000)
    assert [c.valor_comissao for c in _comissoes(db_session)] == [6_400.0] * 3  # (40.000 − 20%) × 20% por parcela


def test_snapshot_preserva_calculo_e_paga_nunca_muda(db_session, professional, client):
    definir_parametros(db_session, impostos=0.15, infra=INFRA_5)
    recebimento = _receber(db_session, professional, "LICENSE", 120_000)
    paga, = _comissoes(db_session)
    paga.status = "PAID"
    db_session.commit()
    _receber(db_session, professional, "INITIAL_ANNUAL_SUBSCRIPTION", 36_000)
    # Parâmetros novos (carga tributária e infraestrutura maiores) a partir de hoje
    client.post("/api/v1/comissoes/perfis-tributarios", json={"regime": "LUCRO_PRESUMIDO", "vigente_de": (HOJE - timedelta(days=1)).isoformat(),
                                                             "componentes": [{"nome": "CARGA", "aliquota": 0.20}]})
    client.post("/api/v1/comissoes/modelos-custo-infra", json={"nome": "Infra 2", "vigente_de": (HOJE - timedelta(days=1)).isoformat(),
                                                              "componentes": [{"categoria": "cloud_cost", "metodo": "PERCENTAGE", "percentual": 0.10}]})
    resposta = client.post("/api/v1/comissoes/recalculo", json={"motivo": "Novos parâmetros"})
    assert resposta.status_code == 200 and resposta.json()["alteradas"] == 1  # só a não paga
    db_session.refresh(paga)
    apuracao = db_session.query(ApuracaoComissao).filter_by(recebimento_governo_id=recebimento.id).one()
    assert (paga.status, paga.valor_comissao) == ("PAID", 19_200.0)
    assert (apuracao.aliquota_tributaria, apuracao.impostos, apuracao.custo_infra, apuracao.margem_comissionavel_liquida) == (
        0.15, Decimal("18000.00"), Decimal("6000.00"), Decimal("96000.00"))
    nao_paga = _comissoes(db_session)[-1]
    assert nao_paga.valor_comissao == 5_040.0  # (36.000 − 20% − 10%) × 20% com os parâmetros novos, por recálculo explícito


def test_waterfall_do_map(db_session, professional, client):
    definir_parametros(db_session, impostos=0.15, infra=INFRA_5)
    _receber(db_session, professional, "LICENSE", 120_000)
    _receber(db_session, professional, "IMPLEMENTATION", 20_000)
    dados = client.get("/api/v1/motor/comissoes/waterfall", params={"agrupar": "tenant"}).json()
    linha = next(item for item in dados["linhas"] if item["chave"] == TENANT)
    assert (linha["receita_bruta"], linha["impostos"], linha["infraestrutura"], linha["margem_comissionavel_liquida"], linha["comissao"],
            linha["margem_cyberfort_apos_comissao"]) == (140_000, 21_000, 7_000, 112_000, 19_200, 92_800)
    assert linha["percentuais"] == {"impostos": 15.0, "infraestrutura": 5.0, "margem_comissionavel_liquida": 80.0, "comissao": 13.71,
                                    "margem_cyberfort_apos_comissao": 66.29}
    for agrupar in ("venda", "representante", "produto", "periodo"):
        assert client.get("/api/v1/motor/comissoes/waterfall", params={"agrupar": agrupar}).json()["total"]["receita_bruta"] == 140_000
    margem = client.get(f"/api/v1/motor/tenants/{TENANT}/margem-contribuicao",
                        params={"inicio": (HOJE - timedelta(days=1)).isoformat(), "fim": (HOJE + timedelta(days=1)).isoformat()}).json()
    assert margem["margem_comissionavel_liquida"] == 112_000 and margem["comissao"] == 19_200


def test_estorno_de_recebimento_no_motor(db_session, professional):
    definir_parametros(db_session, impostos=0.15, infra=INFRA_5)
    recebimento = _receber(db_session, professional, "LICENSE", 40_000)
    assert governo.recebimentos.estornar(db_session, recebimento.id, "Glosa") == {"anuladas": 1, "a_compensar": 0}
    assert _comissoes(db_session)[0].status == "REVERSED"
    assert db_session.query(ApuracaoComissao).one().status == "REVERSED"


def test_parametros_exigem_super_admin(client, criar_usuario_autenticado):
    cabecalho = criar_usuario_autenticado("tenant-outro")
    assert client.get("/api/v1/comissoes/parametros", headers=cabecalho).status_code == 403
    assert client.post("/api/v1/comissoes/recalculo", json={"motivo": "x"}, headers=cabecalho).status_code == 403
