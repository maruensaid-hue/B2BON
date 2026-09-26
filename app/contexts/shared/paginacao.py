"""Paginação por cursor opaco (keyset) para listas da API interna (Fase S0).

O cursor carrega a posição da última linha devolvida, não um deslocamento:
a próxima página continua certa mesmo com inserções no meio, e o banco usa
índice em vez de pular linhas. A resposta continua uma lista; o próximo
cursor vai no header `X-Proximo-Cursor` (ausente na última página).
"""

import base64
import json
from dataclasses import dataclass
from typing import Generic, TypeVar

from fastapi import Response

from app.services.errors import ValidacaoFalhou

T = TypeVar("T")
LIMITE_PADRAO = 100
LIMITE_MAXIMO = 500
HEADER_PROXIMO = "X-Proximo-Cursor"


@dataclass(frozen=True)
class Pagina(Generic[T]):
    itens: list[T]
    proximo_cursor: str | None


def codificar(posicao: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(posicao, separators=(",", ":"), default=str).encode()).decode()


def decodificar(cursor: str | None) -> dict | None:
    if not cursor:
        return None
    try:
        posicao = json.loads(base64.urlsafe_b64decode(cursor.encode()))
    except (ValueError, TypeError) as erro:
        raise ValidacaoFalhou("Cursor inválido.") from erro
    if not isinstance(posicao, dict):
        raise ValidacaoFalhou("Cursor inválido.")
    return posicao


def limite(valor: int | None) -> int:
    if valor is None:
        return LIMITE_PADRAO
    if valor < 1 or valor > LIMITE_MAXIMO:
        raise ValidacaoFalhou(f"limite deve estar entre 1 e {LIMITE_MAXIMO}.")
    return valor


def fatiar(linhas: list[T], quantidade: int, posicao_de) -> Pagina[T]:
    """`linhas` foi buscado com `quantidade + 1`: a sobra indica que há próxima página."""
    if len(linhas) <= quantidade:
        return Pagina(linhas, None)
    itens = linhas[:quantidade]
    return Pagina(itens, codificar(posicao_de(itens[-1])))


def expor(response: Response, pagina: Pagina) -> list:
    if pagina.proximo_cursor:
        response.headers[HEADER_PROXIMO] = pagina.proximo_cursor
    return pagina.itens
