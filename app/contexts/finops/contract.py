"""Contrato público do contexto AI FinOps (Fase 5)."""

from decimal import Decimal

from sqlalchemy.orm import Session

from app.contexts.finops import creditos, dashboard, orcamentos, precos

__all__ = ["creditos", "custear", "dashboard", "orcamentos", "precos"]


def custear(db: Session, modelo: str | None, entrada: int, saida: int, cache_escrita: int, cache_leitura: int, provider: str = "anthropic") -> tuple[Decimal | None, int | None, Decimal | None]:
    """(custo_usd, preco_id, créditos) de uma chamada. `None` quando não há
    preço para o modelo ou a política de créditos está pendente."""
    preco = precos.obter_preco(db, modelo, provider)
    if preco is None:
        return None, None, None
    custo = precos.calcular_custo(preco, entrada, saida, cache_escrita, cache_leitura)
    return custo, preco.id, creditos.creditos_para(custo, creditos.politica_vigente(db))
