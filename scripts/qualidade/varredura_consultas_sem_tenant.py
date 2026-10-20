"""Varredura estática (AST): consultas a modelos com `tenant_id` que NÃO mencionam tenant em lugar nenhum da cadeia.

Cobre `db.query(Modelo)...`, `select/update/delete(Modelo)...` e `db.get(Modelo, id)` (que ignora tenant por construção).
É um detector de CANDIDATOS: cada achado exige triagem (escopo por join, id vindo de objeto já validado, tabela global de fato).
Uso: python scripts/qualidade/varredura_consultas_sem_tenant.py [--json]
"""

from __future__ import annotations

import ast
import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

PASTAS = ["app"]
FUNCOES_QUERY = {"query"}
FUNCOES_SELECT = {"select", "update", "delete"}


def modelos_com_tenant() -> set[str]:
    import app.models  # noqa: F401
    from app.db.base import Base  # type: ignore

    nomes = set()
    for mapper in Base.registry.mappers:
        if "tenant_id" in mapper.columns:
            nomes.add(mapper.class_.__name__)
    return nomes


def _base_do_nome(no: ast.AST) -> str | None:
    while isinstance(no, ast.Attribute):
        no = no.value
    if isinstance(no, ast.Name):
        return no.id
    return None


def _modelos_em(args: list[ast.AST], conhecidos: set[str]) -> set[str]:
    achados: set[str] = set()
    for arg in args:
        for no in ast.walk(arg):
            if isinstance(no, ast.Name) and no.id in conhecidos:
                achados.add(no.id)
    return achados


def _cadeia_completa(no: ast.Call, pais: dict[ast.AST, ast.AST]) -> ast.AST:
    atual: ast.AST = no
    while True:
        pai = pais.get(atual)
        if isinstance(pai, ast.Attribute) and pai.value is atual:
            neto = pais.get(pai)
            if isinstance(neto, ast.Call) and neto.func is pai:
                atual = neto
                continue
        return atual


def varrer_arquivo(caminho: Path, conhecidos: set[str]) -> list[dict]:
    fonte = caminho.read_text(encoding="utf-8")
    arvore = ast.parse(fonte)
    pais = {filho: pai for pai in ast.walk(arvore) for filho in ast.iter_child_nodes(pai)}
    funcoes = {}
    for no in ast.walk(arvore):
        if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for filho in ast.walk(no):
                funcoes.setdefault(filho, no.name)
    achados = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call) or not isinstance(no.func, (ast.Attribute, ast.Name)):
            continue
        nome = no.func.attr if isinstance(no.func, ast.Attribute) else no.func.id
        tipo = None
        if nome in FUNCOES_QUERY and isinstance(no.func, ast.Attribute):
            tipo = "query"
        elif nome in FUNCOES_SELECT and isinstance(no.func, ast.Name):
            tipo = "select"
        elif nome == "get" and isinstance(no.func, ast.Attribute) and no.args and isinstance(no.args[0], ast.Name) and no.args[0].id in conhecidos:
            achados.append({"arquivo": str(caminho.relative_to(RAIZ)), "linha": no.lineno, "funcao": funcoes.get(no, "?"), "tipo": "get",
                            "modelos": [no.args[0].id], "trecho": ast.unparse(no)[:140]})
            continue
        if tipo is None:
            continue
        modelos = _modelos_em(no.args, conhecidos)
        if not modelos:
            continue
        cadeia = _cadeia_completa(no, pais)
        texto = ast.unparse(cadeia)
        if "tenant" in texto.lower():
            continue
        # função inteira menciona tenant_id como parâmetro? (informação para triagem, não filtro)
        achados.append({"arquivo": str(caminho.relative_to(RAIZ)), "linha": no.lineno, "funcao": funcoes.get(no, "?"), "tipo": tipo,
                        "modelos": sorted(modelos), "trecho": texto[:160]})
    return achados


def varrer() -> list[dict]:
    conhecidos = modelos_com_tenant()
    todos: list[dict] = []
    for pasta in PASTAS:
        for arquivo in sorted((RAIZ / pasta).rglob("*.py")):
            if "__pycache__" in arquivo.parts:
                continue
            todos.extend(varrer_arquivo(arquivo, conhecidos))
    return todos


if __name__ == "__main__":
    resultado = varrer()
    if "--json" in sys.argv:
        print(json.dumps(resultado, ensure_ascii=False, indent=1))
    else:
        print(f"{len(resultado)} candidatos; modelos com tenant_id: {len(modelos_com_tenant())}")
