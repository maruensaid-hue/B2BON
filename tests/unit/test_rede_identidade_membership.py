"""Fase 7: regras puras da Business Network (CNPJ e Membership)."""

import pytest

from app.contexts.network import membership
from app.contexts.network.identidade import cnpj_valido, normalizar_cnpj


@pytest.mark.parametrize(
    ("cnpj", "valido"),
    [
        ("11.222.333/0001-81", True),
        ("11444777000161", True),
        ("11222333000182", False),
        ("00000000000000", False),
        ("1122233300018", False),
        (None, False),
    ],
)
def test_cnpj_valido_confere_digitos_verificadores(cnpj, valido):
    assert cnpj_valido(cnpj) is valido


def test_normalizar_cnpj_mantem_so_digitos():
    assert normalizar_cnpj(" 11.222.333/0001-81 ") == "11222333000181"
    assert normalizar_cnpj("") is None


@pytest.mark.parametrize("acao", sorted(membership.ACOES_ADMIN))
def test_acoes_de_identidade_so_para_admin(acao):
    assert membership.pode("admin", acao) and membership.pode("super_admin", acao)
    assert not membership.pode("user", acao)


@pytest.mark.parametrize("acao", sorted(membership.ACOES_MEMBRO))
def test_acoes_do_dia_a_dia_para_qualquer_membro(acao):
    assert membership.pode("user", acao)


def test_acao_desconhecida_e_negada():
    assert not membership.pode("admin", "alterar_plano")
