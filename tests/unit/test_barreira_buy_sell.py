"""Fitness function da barreira Buy/Sell (Fase 10, Master Prompt §50, §80).

Estrutural: nenhum código fora do lado comprador importa o contexto de
procurement nem os modelos dele, nem cita as tabelas por nome em SQL. Só o
próprio contexto, a API do comprador, `app/models` e as migrações conhecem
esses dados. Assim, Sell Side (Bid Intelligence), PREDATOR, CRM, MAP,
Opportunity, Business Network e o Corporate Brain não têm caminho de código
até eles, e a IA desses módulos não tem como recuperá-los.
"""

import ast
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
APP = RAIZ / "app"

MODELOS_COMPRADOR = {
    "orgao_publico", "unidade_compras", "plano_contratacao", "item_pca", "demanda_compra", "processo_contratacao",
    "evento_processo", "fornecedor_compras", "contrato_compra", "evento_contrato_compra", "pesquisa_preco", "documento_compras",
}
PERMITIDOS = (APP / "contexts" / "procurement", APP / "api" / "v1" / "procurement.py", APP / "api" / "v1" / "strategic_sourcing.py", APP / "api" / "v1" / "portal_fornecedor.py", APP / "models")


def _permitido(arquivo: Path) -> bool:
    return any(arquivo == p or p in arquivo.parents for p in PERMITIDOS)


def _imports(arquivo: Path) -> list[str]:
    modulos = []
    for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
        if isinstance(no, ast.Import):
            modulos.extend(a.name for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            modulos.append(no.module)
    return modulos


def _arquivos() -> list[Path]:
    return [p for p in APP.rglob("*.py") if "__pycache__" not in p.parts and not _permitido(p)]


def test_ninguem_fora_do_lado_comprador_importa_procurement():
    violacoes = []
    for arquivo in _arquivos():
        for modulo in _imports(arquivo):
            partes = modulo.split(".")
            if partes[:3] == ["app", "contexts", "procurement"] or (
                partes[:2] == ["app", "models"] and len(partes) > 2 and partes[2] in MODELOS_COMPRADOR
            ):
                violacoes.append(f"{arquivo.relative_to(RAIZ)} importa {modulo}")
    assert violacoes == [], "\n".join(violacoes)


def test_ninguem_fora_do_lado_comprador_cita_tabelas_do_comprador_em_sql():
    padrao = re.compile(r"\b(" + "|".join(sorted(MODELOS_COMPRADOR)) + r")\b")
    violacoes = []
    for arquivo in _arquivos():
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            if isinstance(no, ast.Constant) and isinstance(no.value, str) and padrao.search(no.value):
                violacoes.append(f"{arquivo.relative_to(RAIZ)}: {no.value[:80]!r}")
    assert violacoes == [], "\n".join(violacoes)


def test_lado_comprador_nao_escreve_no_corporate_brain():
    """Conhecimento do Brain com visibilidade "rede" alimenta o Agente
    Corporativo, que responde a outras empresas: procurement não escreve lá."""
    proibidos = ("app.contexts.intelligence.brain", "app.models.conhecimento_corporativo")
    violacoes = [
        f"{arquivo.relative_to(RAIZ)} importa {modulo}"
        for arquivo in (APP / "contexts" / "procurement").rglob("*.py")
        for modulo in _imports(arquivo)
        if modulo in proibidos or modulo.startswith(proibidos)
    ]
    assert violacoes == [], "\n".join(violacoes)
