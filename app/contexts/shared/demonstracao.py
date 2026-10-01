"""Registro de semeadores do ambiente de demonstração (D-082) — Shared Kernel.

Contextos protegidos por barreira (o lado comprador: Public Procurement e Strategic Sourcing) não podem ser importados
por quem monta a demonstração; eles mesmos registram aqui como preencher o próprio pedaço com dados fictícios, e a
demonstração só pede "semeie o que estiver registrado" — o mesmo padrão das ferramentas do Intelligence Agent.
"""

from collections.abc import Callable

from sqlalchemy.orm import Session

Semeador = Callable[[Session, str, int], None]
_SEMEADORES: dict[str, Semeador] = {}


def registrar(nome: str, semeador: Semeador) -> None:
    _SEMEADORES[nome] = semeador


def semear(db: Session, tenant_id: str, usuario_id: int) -> list[str]:
    for nome in sorted(_SEMEADORES):
        _SEMEADORES[nome](db, tenant_id, usuario_id)
    return sorted(_SEMEADORES)
