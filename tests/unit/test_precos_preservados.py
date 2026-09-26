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


# Fase 15: pacotes de AI Credits definidos pelo PO (créditos, R$). A única
# cópia é a semente do catálogo versionado; o frontend lê da API.
PACOTES_AI_CREDITS = {
    "AI_START": (5_000, 99), "AI_15K": (15_000, 249), "AI_30K": (30_000, 449), "AI_75K": (75_000, 899),
    "AI_150K": (150_000, 1499), "AI_350K": (350_000, 2999), "AI_1M": (1_000_000, 6990), "ENTERPRISE": (None, None),
}


def test_pacotes_de_ai_credits_sao_os_do_po():
    from app.contexts.finops.catalogos import SEMENTE_PACOTES

    semente = {codigo: (creditos, int(preco) if preco is not None else None) for codigo, _, creditos, preco, _ in SEMENTE_PACOTES}
    assert semente == PACOTES_AI_CREDITS


def test_frontend_nao_tem_preco_de_pacote_fixo_no_codigo():
    """Preço duplicado no frontend diverge do catálogo na primeira mudança."""
    padrao = re.compile(r"R\$\s?(99|249|449|899|1\.499|2\.999|6\.990)(,00)?\b")
    for arquivo in (RAIZ / "frontend/src").rglob("*.tsx"):
        assert not padrao.search(arquivo.read_text(encoding="utf-8")), f"preço de pacote fixo em {arquivo}"


# Phase I (D-059): planos aprovados pelo PO — (preço R$/mês, usuários incluídos, AI Credits/mês, tipo de preço).
# Public Procurement não tem plano (PENDING_DEFINITION). Usuários do Bid Intelligence: não definido (None).
PLANOS_D059 = {
    "Bid Intelligence": (1490.0, None, 25_000, "FIXED"),
    "Strategic Sourcing": (2990.0, 5, 50_000, "FIXED"),
    "Strategic Sourcing Enterprise": (5990.0, None, 100_000, "STARTING_AT"),
}


def test_planos_d059_sao_os_aprovados_e_procurement_segue_sem_preco():
    import importlib.util

    from app.contexts.finops.comercial import FRANQUIAS, franquia_mensal

    caminho = RAIZ / "alembic/versions/a3c5e7f9b1d2_phase_i_planos_comerciais.py"
    spec = importlib.util.spec_from_file_location("migracao_phase_i", caminho)
    migracao = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migracao)
    migrados = {nome: (preco, usuarios, franquia_mensal(modulos)[0], tipo) for nome, preco, usuarios, modulos, _, tipo in migracao.PLANOS}
    assert migrados == PLANOS_D059
    assert not any("procurement" in modulos for *_, modulos, _, _ in migracao.PLANOS)
    assert FRANQUIAS["procurement"].creditos is None and FRANQUIAS["procurement"].status == "PENDING_FINAL_DEFINITION"
