"""Aritmética financeira do enriquecimento: custo de aquisição, markup, preço de venda, margem e arredondamento.

Tudo em `Decimal`. A precisão interna é de 12 casas (`PRECISAO_INTERNA`; o custo contratual é uma dízima: USD 600 ÷ 6.800 × câmbio) e o único arredondamento aplicado ao guardar um valor por crédito é
esse, em meio-par (`ROUND_HALF_EVEN`), para o custo unitário de um lote. O consumo por pesquisa no razão guarda o valor com a precisão interna.
O valor COBRADO de um pacote (créditos × preço unitário) é arredondado para centavos, meio para cima (`centavos`), a regra financeira do produto.
Fora isso, só a **exibição** arredonda (padrão: 2 casas, meio para cima), conforme o valor de apresentação informado (≈ R$ 1,35)."""

from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal

PRECISAO_INTERNA = Decimal("0.000000000001")
CEM = Decimal(100)


def dec(valor) -> Decimal:
    """Converte sem passar por float (float contaminaria a precisão)."""
    return valor if isinstance(valor, Decimal) else Decimal(str(valor))


def interna(valor: Decimal) -> Decimal:
    return valor.quantize(PRECISAO_INTERNA, rounding=ROUND_HALF_EVEN)


_interna = interna


def custo_unitario(custo_total, quantidade: int) -> Decimal:
    """Custo por crédito do provedor: custo total do lote ÷ quantidade (R$ 269,94 ÷ 400 = R$ 0,67485)."""
    if quantidade <= 0:
        raise ValueError("quantidade de créditos deve ser positiva")
    return _interna(dec(custo_total) / Decimal(quantidade))


def media_ponderada(lotes: list[tuple[Decimal, int]]) -> Decimal:
    """Custo médio por crédito: Σ custo total ÷ Σ quantidade, sobre (custo_total, quantidade) dos lotes."""
    quantidade = sum(q for _, q in lotes)
    if quantidade <= 0:
        raise ValueError("nenhum crédito nos lotes")
    return _interna(sum((dec(c) for c, _ in lotes), Decimal(0)) / Decimal(quantidade))


def preco_unitario(custo_unitario_brl, markup_percentual) -> Decimal:
    """Preço de venda por crédito do provedor: custo × (1 + markup/100). Markup de 100% sobre R$ 0,67485 = R$ 1,3497."""
    return _interna(dec(custo_unitario_brl) * (1 + dec(markup_percentual) / CEM))


def margem_bruta_percentual(markup_percentual) -> Decimal:
    """Margem bruta sobre o preço de venda correspondente a um markup sobre o custo: markup/(100+markup). 100% de markup = 50% de margem."""
    markup = dec(markup_percentual)
    return _interna(markup / (CEM + markup) * CEM)


def valor(creditos: int, unitario) -> Decimal:
    """Valor de `creditos` créditos a `unitario` por crédito, na precisão interna (sem arredondar para centavos)."""
    return _interna(Decimal(creditos) * dec(unitario))


def exibir(valor_brl, casas: int = 2) -> Decimal:
    """Arredondamento APENAS de apresentação (meio para cima)."""
    return dec(valor_brl).quantize(Decimal(1).scaleb(-casas), rounding=ROUND_HALF_UP)


def margem_sobre_venda(venda, custo) -> Decimal:
    """Margem bruta realizada em percentual do valor de venda: (venda − custo) ÷ venda."""
    venda = dec(venda)
    if venda == 0:
        raise ValueError("venda zero")
    return _interna((venda - dec(custo)) / venda * CEM)


CENTAVO = Decimal("0.01")


def centavos(valor_brl) -> Decimal:
    """Regra financeira do produto para valor COBRADO em reais: centavos, meio para cima (a mesma de comissões e tributos). É o que vale para o total
    de um pacote e para o valor enviado ao checkout. Valores internos por crédito seguem na precisão interna."""
    return dec(valor_brl).quantize(CENTAVO, rounding=ROUND_HALF_UP)


def markup_percentual(preco, custo) -> Decimal:
    """Markup realizado sobre o custo: (preço ÷ custo − 1) × 100."""
    custo = dec(custo)
    if custo == 0:
        raise ValueError("custo zero")
    return _interna((dec(preco) / custo - 1) * CEM)
