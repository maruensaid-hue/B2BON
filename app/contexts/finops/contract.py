"""Contrato público do contexto AI FinOps (Fase 5; AI Credits na Fase 15)."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.contexts.finops import (
    carteira,
    catalogos,
    comercial,
    compras,
    creditos,
    dashboard,
    economia,
    execucoes,
    limites,
    orcamentos,
    precos,
    rotinas,
)
from app.contexts.finops.rotinas import creditos_ia_rotina

__all__ = [
    "carteira", "catalogos", "comercial", "compras", "creditos", "custear", "dashboard", "economia", "execucoes", "limites",
    "orcamentos", "precos", "rotinas", "creditos_ia_rotina",
]


def custear(db: Session, modelo: str | None, entrada: int, saida: int, cache_escrita: int, cache_leitura: int,
            provider: str = "anthropic") -> tuple[Decimal | None, int | None, Decimal | None]:
    """(custo_usd, preco_id, economia_cache_usd) de uma chamada. `None` quando
    não há preço para o modelo. A economia de cache é o que a leitura de
    cache deixou de custar em relação a tokens de entrada normais.

    Créditos NÃO vêm mais do custo (Fase 15): vêm do peso do workload."""
    preco = precos.obter_preco(db, modelo, provider)
    if preco is None:
        return None, None, None
    custo = precos.calcular_custo(preco, entrada, saida, cache_escrita, cache_leitura)
    economia_cache = (Decimal(cache_leitura) * (Decimal(str(preco.entrada_usd_mtok)) - Decimal(str(preco.cache_leitura_usd_mtok)))
                      / Decimal(1_000_000))
    return custo, preco.id, economia_cache


def custo_evitado(db: Session, modelo: str | None, entrada: int, saida: int, provider: str = "anthropic") -> Decimal | None:
    """Custo que uma resposta em cache evitou (a chamada inteira)."""
    preco = precos.obter_preco(db, modelo, provider)
    return precos.calcular_custo(preco, entrada, saida) if preco is not None else None
