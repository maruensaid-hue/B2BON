"""Aritmética financeira do enriquecimento: custo unitário, markup, preço, margem, precisão e arredondamento (só de exibição)."""

from decimal import Decimal

import pytest

from app.contexts.enriquecimento import precos


def test_custo_unitario_do_aporte_informado_pelo_po():
    assert precos.custo_unitario(Decimal("269.94"), 400) == Decimal("0.67485000")


def test_markup_de_100_por_cento_dobra_o_custo_e_da_o_preco_de_referencia():
    custo = precos.custo_unitario(Decimal("269.94"), 400)
    assert precos.preco_unitario(custo, 100) == Decimal("1.34970000")


def test_markup_de_100_por_cento_e_50_por_cento_de_margem_bruta_sobre_a_venda():
    assert precos.margem_bruta_percentual(100) == Decimal("50.00000000")
    assert precos.margem_bruta_percentual(0) == Decimal("0E-8") or precos.margem_bruta_percentual(0) == 0
    assert precos.margem_bruta_percentual(Decimal("50")).quantize(Decimal("0.01")) == Decimal("33.33")


def test_exibicao_arredonda_para_2_casas_mas_o_valor_interno_nao():
    preco = Decimal("1.3497")
    assert precos.exibir(preco) == Decimal("1.35")
    assert precos.exibir(preco, 4) == Decimal("1.3497")
    assert precos.exibir(Decimal("1.345")) == Decimal("1.35")  # meio para cima, só na apresentação
    assert preco == Decimal("1.3497")  # o valor interno continua intacto


def test_valor_de_cobranca_nao_e_arredondado_para_centavos():
    unitario = Decimal("1.3497")
    assert precos.valor(3, unitario) == Decimal("4.04910000")  # 3 créditos: R$ 4,0491, não R$ 4,05
    assert precos.valor(400, unitario) == Decimal("539.88000000")


def test_nenhum_calculo_passa_por_float():
    assert precos.dec(0.1) == Decimal("0.1")  # via str: o float 0.1 binário não contamina
    soma = sum((precos.valor(1, "0.1") for _ in range(10)), Decimal(0))
    assert soma == Decimal("1.000000000000")  # em float seria 0.9999999999999999


def test_custo_que_nao_divide_exato_usa_12_casas_meio_par():
    assert precos.custo_unitario(Decimal("100"), 3) == Decimal("33.333333333333")
    assert precos.custo_unitario(Decimal("200"), 3) == Decimal("66.666666666667")


def test_custo_contratual_da_lusha_e_uma_dizima_guardada_em_12_casas():
    """USD 600 ÷ 6.800 créditos = USD 0,088235294; × câmbio de planejamento R$ 6,00 = R$ 0,529411765 por crédito (9 casas na exibição)."""
    usd = precos.interna(Decimal(600) / Decimal(6800))
    brl = precos.interna(Decimal(600) * Decimal(6) / Decimal(6800))
    assert usd == Decimal("0.088235294118") and brl == Decimal("0.529411764706")
    assert precos.exibir(usd, 9) == Decimal("0.088235294") and precos.exibir(brl, 9) == Decimal("0.529411765")
    assert precos.centavos(Decimal(600) * Decimal(6)) == Decimal("3600.00")


def test_media_ponderada_dos_lotes():
    # 400 créditos a R$ 0,67485 e 600 créditos a R$ 0,80 => (269,94 + 480) / 1000
    assert precos.media_ponderada([(Decimal("269.94"), 400), (Decimal("480"), 600)]) == Decimal("0.74994000")


def test_margem_realizada_sobre_a_venda():
    assert precos.margem_sobre_venda(Decimal("1.3497"), Decimal("0.67485")) == Decimal("50.00000000")


@pytest.mark.parametrize("chamada", [lambda: precos.custo_unitario(Decimal("10"), 0), lambda: precos.media_ponderada([]),
                                     lambda: precos.margem_sobre_venda(0, 1)])
def test_entradas_invalidas_sao_recusadas(chamada):
    with pytest.raises(ValueError):
        chamada()
