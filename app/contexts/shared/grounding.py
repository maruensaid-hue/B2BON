"""Grounding de extração por IA em documentos — Shared Kernel (Fases 9-10).

A IA propõe itens com citação e cláusula; aqui o sistema decide o que vale:
a citação tem de estar literalmente numa página do bloco analisado (a página
é calculada, não aceita da IA) e a cláusula só vale se aparecer na página.
"""

import json
import re

from app.contexts.shared.texto import localizar_pagina

CARACTERES_POR_BLOCO = 40_000


def blocos(paginas: list[str], caracteres_por_bloco: int = CARACTERES_POR_BLOCO) -> list[list[int]]:
    resultado: list[list[int]] = []
    atual: list[int] = []
    tamanho = 0
    for indice, pagina in enumerate(paginas):
        if atual and tamanho + len(pagina) > caracteres_por_bloco:
            resultado.append(atual)
            atual, tamanho = [], 0
        atual.append(indice)
        tamanho += len(pagina)
    if atual:
        resultado.append(atual)
    return resultado


def corpo_do_bloco(paginas: list[str], bloco: list[int]) -> str:
    return "\n".join(f"[[página {i + 1}]]\n{paginas[i]}" for i in bloco)


def itens_json(conteudo: str) -> list[dict]:
    achado = re.search(r"\[.*\]", conteudo, re.DOTALL)
    if achado is None:
        return []
    try:
        itens = json.loads(achado.group(0))
    except json.JSONDecodeError:
        return []
    return [i for i in itens if isinstance(i, dict)] if isinstance(itens, list) else []


def ancorar(paginas: list[str], bloco: list[int], citacao: str) -> int | None:
    """Página absoluta (1-based) da citação dentro do bloco, ou None."""
    if not citacao:
        return None
    relativa = localizar_pagina([paginas[i] for i in bloco], citacao)
    return bloco[relativa - 1] + 1 if relativa is not None else None


def clausula_valida(clausula: object, pagina_texto: str) -> str | None:
    if not isinstance(clausula, str):
        return None
    clausula = clausula.strip()[:40]
    if not clausula or not re.search(r"\w", clausula):
        return None
    return clausula if clausula.lower() in pagina_texto.lower() else None
