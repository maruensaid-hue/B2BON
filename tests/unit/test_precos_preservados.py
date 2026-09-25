"""Preços preservados (Fase 14, regra do Master Prompt: não alterar nem
inventar preço). Congela os valores vigentes e confere as três cópias que
existem hoje (OI-003): página pública, seed de planos de suíte e migração
dos planos avulsos. Mudar um preço exige instrução do PO e a atualização
consciente deste teste."""

import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

# Valores vigentes (PRICING_CURRENT_STATE.md §2), em R$/mês.
PRECOS = {
    "Starter": 924.50, "Professional": 1664.10, "Enterprise": 2958.40,
    "MAP Starter": 149.50, "MAP Professional": 269.10, "MAP Enterprise": 478.40,
    "PREDATOR Starter": 475.50, "PREDATOR Professional": 855.90, "PREDATOR Enterprise": 1521.60,
    "CRM Starter": 299.50, "CRM Professional": 539.10, "CRM Enterprise": 958.40,
}


def _reais(texto: str) -> float:
    return float(texto.replace(".", "").replace(",", "."))


def test_pagina_publica_anuncia_os_precos_vigentes():
    fonte = (RAIZ / "frontend/src/pages/Planos.tsx").read_text(encoding="utf-8")
    anunciados = {}
    for preco, nome in re.findall(r'preco: "R\$ ([\d.,]+)/mês",\s*checkoutPlanoNome: "([^"]+)"', fonte):
        anunciados[nome] = _reais(preco)
    for total, nome in re.findall(r'total: "R\$ ([\d.,]+)",[^}]*?checkoutPlanoNome: "([^"]+)"', fonte, re.DOTALL):
        anunciados[nome] = _reais(total)
    assert anunciados == PRECOS


def test_seed_e_migracao_cobram_os_mesmos_precos():
    seed = (RAIZ / "scripts/bootstrap_tenant.py").read_text(encoding="utf-8")
    suites = {nome: float(preco) for nome, preco in re.findall(r'"nome": "([^"]+)",[^\n]*"preco_mensal": ([\d.]+)', seed)}
    migracao = (RAIZ / "alembic/versions/807d7076f1df_contratacao_avulsa_por_modulo.py").read_text(encoding="utf-8")
    avulsos = {nome: float(preco) for nome, preco in re.findall(r'\("([A-Z]+ \w+)", ([\d.]+), \d+, "\w+"\)', migracao)}
    cobrados = {k: v for k, v in {**suites, **avulsos}.items() if k in PRECOS}
    assert cobrados == PRECOS
