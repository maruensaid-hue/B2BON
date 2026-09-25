"""§82 — NO UNMETERED AI CALL (fitness function, Fase 4).

Nenhum código de `app/` chama o LLM por fora do AI Gateway:
- `.generate(` só em `app/llm/` (a porta) e em `llm_helpers` (usado só pelo gateway);
- `llm_helpers.gerar` só dentro de `app/contexts/intelligence/gateway.py`;
- o SDK `anthropic` só é importado em `app/llm/claude_provider.py`.
"""

import ast
from pathlib import Path

APP = Path(__file__).resolve().parents[2] / "app"
GATEWAY = APP / "contexts" / "intelligence" / "gateway.py"
LLM_HELPERS = APP / "services" / "llm_helpers.py"


def _arquivos():
    return [p for p in APP.rglob("*.py") if "__pycache__" not in p.parts]


def test_ninguem_chama_generate_fora_da_porta_de_llm():
    violacoes = []
    for arquivo in _arquivos():
        if arquivo.is_relative_to(APP / "llm") or arquivo == LLM_HELPERS:
            continue
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute) and no.func.attr == "generate":
                violacoes.append(f"{arquivo.relative_to(APP)}:{no.lineno}")
    assert violacoes == [], violacoes


def test_llm_helpers_gerar_so_e_usado_pelo_gateway():
    violacoes = []
    for arquivo in _arquivos():
        if arquivo in (GATEWAY, LLM_HELPERS):
            continue
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            if isinstance(no, ast.Attribute) and no.attr in ("gerar", "gerar_e_registrar") and isinstance(no.value, ast.Name) and no.value.id == "llm_helpers":
                violacoes.append(f"{arquivo.relative_to(APP)}:{no.lineno}")
            if isinstance(no, ast.ImportFrom) and no.module == "app.services.llm_helpers":
                violacoes.append(f"{arquivo.relative_to(APP)}:{no.lineno} importa llm_helpers")
    assert violacoes == [], violacoes


def test_sdk_anthropic_so_no_provider():
    violacoes = []
    for arquivo in _arquivos():
        if arquivo == APP / "llm" / "claude_provider.py":
            continue
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            nomes = [a.name for a in no.names] if isinstance(no, ast.Import) else ([no.module] if isinstance(no, ast.ImportFrom) and no.module else [])
            if any(n == "anthropic" or n.startswith("anthropic.") for n in nomes):
                violacoes.append(f"{arquivo.relative_to(APP)}:{no.lineno}")
    assert violacoes == [], violacoes


def test_toda_feature_usada_no_codigo_esta_registrada():
    from app.contexts.intelligence.registro import FEATURES

    usadas = set()
    for arquivo in _arquivos():
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            if isinstance(no, ast.Call) and getattr(no.func, "attr", getattr(no.func, "id", None)) == "ContextoIA":
                for kw in no.keywords:
                    if kw.arg == "feature" and isinstance(kw.value, ast.Constant):
                        usadas.add(kw.value.value)
    assert usadas, "nenhuma chamada ao gateway encontrada"
    assert usadas <= set(FEATURES), usadas - set(FEATURES)
    assert len(usadas) >= 14
