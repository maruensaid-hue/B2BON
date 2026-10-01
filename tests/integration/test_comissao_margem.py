"""D-074/D-076: comissão sobre a Margem Comissionável Líquida = receita recebida − impostos atribuíveis − infraestrutura
PROVISIONADA atribuível (Infrastructure Cost Pool). Alíquotas e custos aqui são de teste.

Cenário: o órgão é o único tenant com tier (Professional, peso 2) e o pool provisionado é R$ 1.000/mês, então o tenant
carrega R$ 1.000/mês. A subscrição anual remunera 12 meses de operação (R$ 12.000); licença e implantação, nenhum."""

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
from tests.parametros_comissao import componente, definir_parametros

RAIZ = Path(__file__).resolve().parents[2]
TENANT = "orgao-margem"
HOJE = date.today()
POOL_1000 = [componente(1000.0)]


def _mig():
    spec = importlib.util.spec_from_file_location("mig_gov", RAIZ / "alembic/versions/d9e1f3a5b7c9_b2bon_government.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@pytest.fixture()
def professional(db_session):
    mig = _mig()
    nome, licenca, implantacao, assinatura, creditos, recomendado = mig.PLANOS[1]
    plano = Plano(nome=nome, franquia_contas_mes=3_000, preco_mensal=0.0, visivel_self_service=False, modulos_contratados=["procurement"],
                  tier_infraestrutura="PROFESSIONAL",
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


def _parametros(db, impostos=0.15, pool=None):
    """Só os planos com tier entram na alocação (o tenant padrão dos testes de API não tem)."""
    definir_parametros(db, impostos=impostos, pool=pool if pool is not None else POOL_1000, tier_padrao=None)


def _apuracao(db, recebimento):
    return db.query(ApuracaoComissao).filter_by(recebimento_governo_id=recebimento.id).one()


def _comissoes(db, **filtro):
    return db.query(ComissaoRepresentante).filter_by(**filtro).order_by(ComissaoRepresentante.id).all()


def test_licenca_e_subscricao_inicial_20_da_margem_e_nao_do_bruto(db_session, professional):
    _parametros(db_session)
    licenca = _apuracao(db_session, _receber(db_session, professional, "LICENSE", 120_000))
    subscricao = _apuracao(db_session, _receber(db_session, professional, "INITIAL_ANNUAL_SUBSCRIPTION", 36_000))
    assert (licenca.meses_infra, licenca.custo_infra, subscricao.meses_infra, subscricao.custo_infra) == (
        0.0, Decimal("0.00"), 12.0, Decimal("12000.00"))
    valores = {c.componente_tipo: (c.base_calculo, c.taxa, c.valor_comissao, c.status) for c in _comissoes(db_session)}
    # licença: 120.000 − 18.000 = 102.000 → 20.400; subscrição: 36.000 − 5.400 − 12.000 = 18.600 → 3.720
    assert valores == {"LICENSE": (102_000.0, 0.2, 20_400.0, "PAYABLE"), "INITIAL_ANNUAL_SUBSCRIPTION": (18_600.0, 0.2, 3_720.0, "PAYABLE")}
    assert sum(v[2] for v in valores.values()) != 156_000 * 0.2


def test_impostos_e_infraestrutura_provisionada_descontados_antes_da_comissao(db_session, professional):
    _parametros(db_session, impostos=0.1133)
    apuracao = _apuracao(db_session, _receber(db_session, professional, "INITIAL_ANNUAL_SUBSCRIPTION", 36_000))
    assert (apuracao.impostos, apuracao.custo_infra, apuracao.margem_comissionavel_liquida) == (
        Decimal("4078.80"), Decimal("12000.00"), Decimal("19921.20"))
    assert _comissoes(db_session)[0].valor_comissao == 3_984.24


def test_custo_de_ia_descontado_antes_da_comissao_quando_a_politica_manda_sem_contar_duas_vezes(db_session, professional, monkeypatch):
    _parametros(db_session, pool=[componente(0.0), componente(5000.0, fornecedor="LLM", servico="Modelos", categoria="AI",
                                                                    contabilizacao="AI_COST")])
    comissoes.politica.nova(db_session, {"deduzir_custo_ia": True}, "PO: IA entra na margem", "teste")
    monkeypatch.setattr(comissoes.infraestrutura, "custo_ia_brl", lambda db, tenant, inicio, fim: (Decimal("1200.00"), None))
    primeira = _apuracao(db_session, _receber(db_session, professional, "LICENSE", 40_000))
    # IA vem do ledger (1.200); o componente AI_COST do pool (5.000) não entra de novo como infraestrutura
    assert (primeira.custo_ia, primeira.custo_infra, primeira.margem_comissionavel_liquida) == (
        Decimal("1200.00"), Decimal("0.00"), Decimal("32800.00"))
    segunda = _apuracao(db_session, _receber(db_session, professional, "LICENSE", 40_000))  # o custo de IA já atribuído não se repete
    assert segunda.custo_ia == 0 and segunda.margem_comissionavel_liquida == Decimal("34000.00")
    with pytest.raises(Exception, match="AI_COST"):
        comissoes.infraestrutura.criar(db_session, componente(1.0, categoria="AI", contabilizacao="INFRASTRUCTURE"), "teste")


def test_custo_de_ia_medido_mas_fora_da_margem_sem_a_politica(db_session, professional, monkeypatch):
    _parametros(db_session, pool=[componente(0.0)])
    monkeypatch.setattr(comissoes.infraestrutura, "custo_ia_brl", lambda db, tenant, inicio, fim: (Decimal("1200.00"), None))
    apuracao = _apuracao(db_session, _receber(db_session, professional, "LICENSE", 40_000))
    assert (apuracao.custo_ia, apuracao.margem_comissionavel_liquida) == (Decimal("1200.00"), Decimal("34000.00"))
    assert apuracao.detalhe["politica_margem"] == {"versao": 1, "deduzir_custo_ia": False}


def test_renovacao_10_da_margem_em_todas(db_session, professional):
    _parametros(db_session)
    for valor in (None, 37_800):
        periodo = governo.contratos.renovar(db_session, professional.id, valor_assinatura=valor,
                                            motivo_reajuste="Cláusula de reajuste" if valor else None)
        componente_ = next(c for c in governo.contratos.componentes(db_session, professional) if c.periodo_id == periodo.id)
        governo.recebimentos.registrar(db_session, professional.id, componente_id=componente_.id, valor=componente_.valor, recebido_em=HOJE)
    # (36.000 − 5.400 − 12.000) × 10% = 1.860; (37.800 − 5.670 − 12.000) × 10% = 2.013
    assert [(c.numero_renovacao, c.taxa, c.valor_comissao) for c in _comissoes(db_session)] == [(1, 0.1, 1_860.0), (2, 0.1, 2_013.0)]


def test_sem_tax_profile_aguarda_e_depois_calcula_sozinho(db_session, professional, client):
    comissoes.infraestrutura.criar(db_session, POOL_1000[0], "teste")
    db_session.commit()
    apuracao = _apuracao(db_session, _receber(db_session, professional, "LICENSE", 120_000))
    comissao = _comissoes(db_session)[0]
    assert (apuracao.status, apuracao.parametros_faltantes) == ("AWAITING_COST_PARAMETERS", ["TAX_PROFILE"])
    assert (comissao.status, comissao.taxa, comissao.valor_comissao) == ("AWAITING_COST_PARAMETERS", 0.2, 0.0)
    resposta = client.post("/api/v1/comissoes/perfis-tributarios", json={
        "regime": "LUCRO_PRESUMIDO", "vigente_de": "2000-01-01",
        "componentes": [{"nome": "IRPJ", "aliquota": 0.05}, {"nome": "CSLL", "aliquota": 0.03}, {"nome": "PIS_COFINS", "aliquota": 0.07}]})
    assert resposta.status_code == 201 and resposta.json()["aguardando_calculadas"] == 1
    db_session.refresh(comissao)
    assert (comissao.status, comissao.valor_comissao) == ("PAYABLE", 20_400.0)


def test_sem_infraestrutura_aguarda_awaiting_infrastructure_cost(db_session, professional, client):
    comissoes.tributos.criar(db_session, {"regime": "LUCRO_PRESUMIDO", "vigente_de": date(2000, 1, 1),
                                          "componentes": [{"nome": "CARGA", "aliquota": 0.15}]}, "teste")
    db_session.commit()
    apuracao = _apuracao(db_session, _receber(db_session, professional, "LICENSE", 120_000))
    assert (apuracao.status, apuracao.parametros_faltantes, apuracao.impostos) == ("AWAITING_COST_PARAMETERS", ["INFRASTRUCTURE_COST"],
                                                                                   Decimal("18000.00"))
    assert _comissoes(db_session)[0].status == "AWAITING_COST_PARAMETERS"
    assert client.get("/api/v1/comissoes/apuracoes").json()[0]["commission_amount_status"] == "AWAITING_INFRASTRUCTURE_COST"


def test_implantacao_nao_comissiona_e_parcelas_sao_proporcionais(db_session, professional):
    _parametros(db_session)
    _receber(db_session, professional, "IMPLEMENTATION", 20_000)
    assert _comissoes(db_session) == []
    assert db_session.query(ApuracaoComissao).count() == 1  # apurada para o MAP mesmo sem comissão
    for _ in range(3):
        _receber(db_session, professional, "LICENSE", 40_000)
    assert [c.valor_comissao for c in _comissoes(db_session)] == [6_800.0] * 3  # (40.000 − 15%) × 20% por parcela
    metade = [_apuracao(db_session, _receber(db_session, professional, "INITIAL_ANNUAL_SUBSCRIPTION", 18_000)) for _ in range(2)]
    # cada metade remunera 6 meses de operação: (18.000 − 2.700 − 6.000) × 20% = 1.860
    assert [(a.meses_infra, a.custo_infra) for a in metade] == [(6.0, Decimal("6000.00"))] * 2
    assert [c.valor_comissao for c in _comissoes(db_session)][-2:] == [1_860.0, 1_860.0]


def test_snapshot_preserva_calculo_e_paga_nunca_muda(db_session, professional, client):
    _parametros(db_session)
    recebimento = _receber(db_session, professional, "LICENSE", 120_000)
    paga, = _comissoes(db_session)
    paga.status = "PAID"
    db_session.commit()
    _receber(db_session, professional, "INITIAL_ANNUAL_SUBSCRIPTION", 36_000)
    # Parâmetros novos: carga tributária maior a partir de ontem e plano de referência mais caro (auditado)
    client.post("/api/v1/comissoes/perfis-tributarios", json={"regime": "LUCRO_PRESUMIDO", "vigente_de": (HOJE - timedelta(days=1)).isoformat(),
                                                             "componentes": [{"nome": "CARGA", "aliquota": 0.20}]})
    componente_id = client.get("/api/v1/comissoes/infraestrutura").json()["componentes"][0]["id"]
    resposta = client.patch(f"/api/v1/comissoes/infraestrutura/componentes/{componente_id}",
                            json={"dados": {"custo_referencia": 2000}, "motivo": "Plano de referência novo"})
    assert resposta.status_code == 200
    resposta = client.post("/api/v1/comissoes/recalculo", json={"motivo": "Novos parâmetros"})
    assert resposta.status_code == 200 and resposta.json()["alteradas"] == 0  # D-077: PAYABLE e PAID nunca são recalculadas
    db_session.refresh(paga)
    apuracao = _apuracao(db_session, recebimento)
    assert (paga.status, paga.valor_comissao) == ("PAID", 20_400.0)
    assert (apuracao.aliquota_tributaria, apuracao.impostos, apuracao.custo_infra, apuracao.margem_comissionavel_liquida) == (
        0.15, Decimal("18000.00"), Decimal("0.00"), Decimal("102000.00"))
    nao_paga = _comissoes(db_session)[-1]
    assert (nao_paga.status, nao_paga.valor_comissao) == ("PAYABLE", 3_720.0)  # valor final: preço novo não a altera
    # um recebimento novo usa os parâmetros novos: (36.000 − 7.200 − 24.000) × 20% = 960
    renovacao = governo.contratos.renovar(db_session, professional.id)
    componente_ = next(c for c in governo.contratos.componentes(db_session, professional) if c.periodo_id == renovacao.id)
    governo.recebimentos.registrar(db_session, professional.id, componente_id=componente_.id, valor=componente_.valor, recebido_em=HOJE)
    assert _comissoes(db_session)[-1].base_calculo == 4_800.0


def test_waterfall_do_map_separa_custo_real_e_provisionado(db_session, professional, client):
    _parametros(db_session, pool=[componente(1000.0, custo_real=600.0)])
    _receber(db_session, professional, "LICENSE", 120_000)
    _receber(db_session, professional, "IMPLEMENTATION", 20_000)
    _receber(db_session, professional, "INITIAL_ANNUAL_SUBSCRIPTION", 36_000)
    dados = client.get("/api/v1/motor/comissoes/waterfall", params={"agrupar": "tenant"}).json()
    linha = next(item for item in dados["linhas"] if item["chave"] == TENANT)
    assert (linha["receita_bruta"], linha["impostos"], linha["infraestrutura"], linha["infraestrutura_real"], linha["custo_ia"],
            linha["margem_comissionavel_liquida"], linha["comissao"], linha["margem_cyberfort_apos_comissao"]) == (
        176_000, 26_400, 12_000, 7_200, 0, 137_600, 24_120, 113_480)
    assert (linha["margem_contribuicao_real"], linha["margem_contribuicao_conservadora"], linha["reserva_infraestrutura"]) == (
        142_400, 137_600, 4_800)
    assert linha["percentuais"]["infraestrutura"] == 6.82 and linha["percentuais"]["infraestrutura_real"] == 4.09
    for agrupar in ("venda", "representante", "produto", "periodo"):
        assert client.get("/api/v1/motor/comissoes/waterfall", params={"agrupar": agrupar}).json()["total"]["receita_bruta"] == 176_000
    margem = client.get(f"/api/v1/motor/tenants/{TENANT}/margem-contribuicao",
                        params={"inicio": (HOJE - timedelta(days=1)).isoformat(), "fim": (HOJE + timedelta(days=1)).isoformat()}).json()
    assert margem["margem_comissionavel_liquida"] == 137_600 and margem["comissao"] == 24_120


def test_estorno_de_recebimento_no_motor(db_session, professional):
    _parametros(db_session)
    recebimento = _receber(db_session, professional, "LICENSE", 40_000)
    assert governo.recebimentos.estornar(db_session, recebimento.id, "Glosa") == {"anuladas": 1, "a_compensar": 0}
    assert _comissoes(db_session)[0].status == "REVERSED"
    assert db_session.query(ApuracaoComissao).one().status == "REVERSED"


def test_parametros_exigem_super_admin(client, criar_usuario_autenticado):
    cabecalho = criar_usuario_autenticado("tenant-outro")
    assert client.get("/api/v1/comissoes/parametros", headers=cabecalho).status_code == 403
    assert client.get("/api/v1/comissoes/infraestrutura", headers=cabecalho).status_code == 403
    assert client.post("/api/v1/comissoes/recalculo", json={"motivo": "x"}, headers=cabecalho).status_code == 403
