"""Fórmulas oficiais de economia de cliente do MAP (LTV, CAC, churn, ROI = razão LTV/CAC, CS Score): coerência, dados ausentes e denominadores zero.

Definições adotadas (as mesmas do código e da documentação em `docs/b2bon/REVENUE_INTELLIGENCE_METRICS.md`, seção "Economia de cliente"):
- LTV médio = valor ganho acumulado das contas-clientes ÷ número de contas-clientes;
- CAC = custo de aquisição do período ÷ novos clientes do período (só do tenant inteiro; por vendedor é sempre nulo);
- Churn do período = clientes DA BASE INICIAL que cancelaram no período ÷ clientes ativos no início do período;
- ROI = razão LTV ÷ CAC."""

from datetime import datetime
from types import SimpleNamespace

import pytest

from app.contexts.map import economics

INICIO = datetime(2026, 10, 1)


def _cliente(desde, cancelado=None, id=0):
    return SimpleNamespace(id=id, cliente_desde=desde, cliente_cancelado_em=cancelado)


class _Fonte:
    def __init__(self, contas, ganho=None, custo=None, nps=None):
        self._contas, self._ganho, self._custo, self._nps = contas, ganho or {}, custo, nps or []

    def contas(self, tenant_id, vendedor_usuario_id=None):
        return self._contas

    def valor_ganho_por_conta(self, tenant_id, conta_ids):
        return {i: self._ganho.get(i, 0.0) for i in conta_ids if i in self._ganho}

    def custo_aquisicao(self, tenant_id, periodo):
        return self._custo

    def notas_nps(self, tenant_id, conta_ids):
        return self._nps


def _economia(contas, periodo="2026-10", vendedor=None, **kw):
    return economics.dashboard_economia(_Fonte(contas, **kw), lambda c: 20.0, "t", periodo, vendedor)


# --- Churn -------------------------------------------------------------------------------------------------------------------------------


def test_churn_conta_so_a_base_inicial_cliente_que_entrou_e_saiu_no_mesmo_mes_nao_infla_a_taxa():
    contas = [
        _cliente(datetime(2026, 1, 10), id=1),                                     # na base inicial, continua cliente
        _cliente(datetime(2026, 10, 3), datetime(2026, 10, 20), id=2),             # entrou e cancelou dentro do mês
        _cliente(datetime(2026, 10, 5), datetime(2026, 10, 25), id=3),             # idem
    ]

    e = _economia(contas)

    assert e["clientes_ativos_inicio_periodo"] == 1
    assert e["taxa_churn"] == 0.0  # ninguém da base inicial cancelou (antes dava 200%: 2 cancelados ÷ 1 ativo)
    assert e["clientes_cancelados_periodo"] == 2  # o total de cancelamentos continua visível...
    assert e["cancelados_da_base_inicial"] == 0   # ...mas a taxa usa só a coorte do denominador


def test_churn_nunca_passa_de_100_por_cento():
    contas = [_cliente(datetime(2026, 1, 1), datetime(2026, 10, 9), id=1)] + [
        _cliente(datetime(2026, 10, d), datetime(2026, 10, d + 1), id=10 + d) for d in range(2, 9)
    ]
    assert 0.0 <= _economia(contas)["taxa_churn"] <= 1.0
    assert _economia(contas)["taxa_churn"] == 1.0


def test_churn_da_base_inicial_proporcional():
    contas = [_cliente(datetime(2026, 1, 1), id=i) for i in range(1, 5)] + [_cliente(datetime(2026, 2, 1), datetime(2026, 10, 15), id=9)]
    assert _economia(contas)["taxa_churn"] == pytest.approx(1 / 5)


def test_cliente_cancelado_antes_do_periodo_nao_esta_na_base_inicial():
    contas = [_cliente(datetime(2026, 1, 1), datetime(2026, 9, 15), id=1), _cliente(datetime(2026, 1, 1), id=2)]
    e = _economia(contas)
    assert (e["clientes_ativos_inicio_periodo"], e["taxa_churn"]) == (1, 0.0)


def test_sem_base_inicial_o_churn_e_nulo_e_nao_zero_nem_erro_de_divisao():
    e = _economia([_cliente(datetime(2026, 10, 5), id=1)])
    assert e["taxa_churn"] is None and e["clientes_ativos_inicio_periodo"] == 0


# --- LTV, CAC, ROI -----------------------------------------------------------------------------------------------------------------------


def test_sem_clientes_ltv_cac_e_roi_sao_nulos():
    e = _economia([], custo=1000.0)
    assert (e["ltv_medio"], e["cac"], e["roi"], e["novos_clientes"]) == (None, None, None, 0)


def test_cac_e_o_custo_do_periodo_dividido_pelos_novos_clientes():
    contas = [_cliente(datetime(2026, 10, 2), id=1), _cliente(datetime(2026, 10, 9), id=2), _cliente(datetime(2026, 1, 1), id=3)]
    e = _economia(contas, custo=3000.0, ganho={1: 5000.0, 2: 7000.0, 3: 0.0})
    assert e["cac"] == 1500.0 and e["novos_clientes"] == 2
    assert e["ltv_medio"] == pytest.approx(12000.0 / 3) and e["roi"] == pytest.approx(4000.0 / 1500.0)


def test_custo_zero_com_novos_clientes_e_cac_zero_valido_e_roi_nulo_sem_dividir_por_zero():
    e = _economia([_cliente(datetime(2026, 10, 2), id=1)], custo=0.0, ganho={1: 100.0})
    assert e["cac"] == 0.0 and e["roi"] is None


def test_custo_nao_informado_deixa_cac_e_roi_nulos():
    e = _economia([_cliente(datetime(2026, 10, 2), id=1)], custo=None, ganho={1: 100.0})
    assert (e["cac"], e["roi"]) == (None, None)


def test_ltv_zero_com_cac_positivo_e_roi_zero_e_nao_sem_dado():
    assert economics.calcular_roi(0.0, 100.0) == 0.0
    assert economics.calcular_roi(None, 100.0) is None and economics.calcular_roi(100.0, None) is None and economics.calcular_roi(100.0, 0) is None


def test_por_vendedor_cac_e_roi_nunca_sao_calculados():
    e = _economia([_cliente(datetime(2026, 10, 2), id=1)], custo=500.0, ganho={1: 900.0}, vendedor=7)
    assert (e["cac"], e["roi"]) == (None, None) and e["ltv_medio"] == 900.0


# --- CS Score ------------------------------------------------------------------------------------------------------------------------------


def test_cs_score_com_apenas_um_dos_componentes_ou_nenhum():
    assert economics.calcular_cs_score([], [])["cs_score"] is None
    assert economics.calcular_cs_score([8, 10], [])["cs_score"] == pytest.approx(90.0)  # só NPS: média 9 → 90
    assert economics.calcular_cs_score([], [20.0, 40.0])["cs_score"] == pytest.approx(70.0)  # só saúde: 100 − risco médio
    assert economics.calcular_cs_score([10], [0.0])["cs_score"] == pytest.approx(100.0)


# --- Período -----------------------------------------------------------------------------------------------------------------------------


def test_periodo_de_dezembro_fecha_no_dia_31():
    assert economics._limites_periodo("2026-12")[1].isoformat() == "2026-12-31"
    assert economics._limites_periodo("2028-02")[1].isoformat() == "2028-02-29"


@pytest.mark.parametrize("periodo", ["abc", "2026-13", "2026-00", "2026", "26-10", "2026-1", "2026-10-01", ""])
def test_periodo_invalido_e_recusado_com_422_na_api(client, periodo):
    assert client.get("/api/v1/crm/dashboard/economia", params={"periodo": periodo}).status_code == 422


def test_periodo_valido_continua_funcionando_na_api(client):
    resposta = client.get("/api/v1/crm/dashboard/economia", params={"periodo": "2026-10"})
    assert resposta.status_code == 200 and {"taxa_churn", "cancelados_da_base_inicial"} <= set(resposta.json())
