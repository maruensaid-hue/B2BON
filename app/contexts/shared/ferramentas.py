"""Registro de ferramentas do B2B ON Intelligence Agent — Shared Kernel (Fase 12).

Cada contexto registra as próprias ferramentas aqui (inversão de
dependência): o orquestrador (Intelligence) não importa nenhum contexto de
negócio, e o lado comprador registra as dele de dentro dele (barreira
Buy/Sell). A validação contra o registro de ferramentas declaradas
(sensibilidade, módulo, agente) é feita pelo orquestrador e por teste.
"""

from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Parametro:
    nome: str
    padrao: str | None = None  # regex com 1 grupo; None = texto livre da pergunta
    obrigatorio: bool = True


@dataclass(frozen=True)
class ContextoFerramenta:
    tenant_id: str
    usuario_id: int | None
    papel: str


@dataclass(frozen=True)
class FerramentaExecutavel:
    nome: str
    agente: str
    lado: str  # SELL | BUY | NEUTRO
    palavras_chave: tuple[str, ...]
    parametros: tuple[Parametro, ...] = ()
    papeis: tuple[str, ...] | None = None
    executar: Callable | None = None
    exemplo: str = ""
    extras: dict = field(default_factory=dict, compare=False)


_REGISTRO: dict[str, FerramentaExecutavel] = {}


def registrar(ferramenta: FerramentaExecutavel) -> None:
    _REGISTRO[ferramenta.nome] = ferramenta


def registradas() -> dict[str, FerramentaExecutavel]:
    return dict(_REGISTRO)
