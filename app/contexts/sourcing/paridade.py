"""Leitura dupla das tabelas unificadas (S3, D-055) — parte neutra.

As tabelas antigas continuam respondendo. Depois de cada leitura, o
repositório do lado pede aqui a comparação: as linhas novas (sempre filtradas
pelo tenant **e pelo lado de quem pergunta**) têm de bater com o mapeamento
das linhas antigas. Divergência:
- COMPARAR (produção): log `SOURCING_DIVERGENCIA` e segue com o dado antigo;
- ESTRITA (testes): `DivergenciaSourcing`;
- DESLIGADA: não compara.

Referências a pais são comparadas pela origem (`("licitacao", 7)`), não pelo
id novo. `criado_em` não entra (é informativo e pode chegar depois).
"""

import json
import logging
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contexts.sourcing.espelho import REFERENCIAS, TABELAS, modo_leitura_dupla
from app.contexts.sourcing.tipos import Lado

logger = logging.getLogger("b2bon.sourcing")
IGNORADOS = {"criado_em"}


class DivergenciaSourcing(Exception):
    pass


def _normalizar(valor):
    if isinstance(valor, bool) or valor is None or isinstance(valor, str):
        return valor
    if isinstance(valor, float | int | Decimal):
        return round(float(valor), 2)
    if isinstance(valor, datetime):
        return valor.replace(tzinfo=None).isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    if isinstance(valor, dict | list):
        return json.dumps(valor, sort_keys=True, default=str)
    return valor


def ativa() -> bool:
    return modo_leitura_dupla() != "DESLIGADA"


def _linhas(db: Session, tabela: str, lado: Lado, tenant_id: str, origem_tabela: str, ids: list[int]) -> dict:
    t = TABELAS[tabela]
    consulta = select(t).where(t.c.lado == lado.value, t.c.tenant_id == tenant_id, t.c.origem_tabela == origem_tabela,
                               t.c.origem_id.in_(ids))
    resultado: dict = {}
    for linha in db.execute(consulta).mappings():
        resultado.setdefault(linha["origem_id"], []).append(dict(linha))
    return resultado


def origens(db: Session, tabela: str, ids: set[int]) -> dict[int, tuple[str, int]]:
    """id novo → (origem_tabela, origem_id), numa consulta por tabela referenciada."""
    if not ids:
        return {}
    t = TABELAS[tabela]
    return {linha.id: (linha.origem_tabela, linha.origem_id)
            for linha in db.execute(select(t.c.id, t.c.origem_tabela, t.c.origem_id).where(t.c.id.in_(ids)))}


def comparar(db: Session, tabela: str, lado: Lado, tenant_id: str, origem_tabela: str, esperados: dict[int, dict | list[dict]]) -> list[str]:
    """`esperados`: origem_id → valores mapeados (ou lista, para requisitos por posição)."""
    if not esperados:
        return []
    novos = _linhas(db, tabela, lado, tenant_id, origem_tabela, list(esperados))
    referencias_usadas = {chave for valores in esperados.values() for item in (valores if isinstance(valores, list) else [valores])
                          for chave in item if chave in REFERENCIAS}
    por_referencia = {chave: origens(db, REFERENCIAS[chave][0], {linha[REFERENCIAS[chave][1]] for linhas in novos.values() for linha in linhas
                                                            if linha[REFERENCIAS[chave][1]] is not None})
               for chave in referencias_usadas}
    divergencias: list[str] = []
    for origem_id, esperado in esperados.items():
        lista_esperada = esperado if isinstance(esperado, list) else [esperado]
        obtidos = sorted(novos.get(origem_id, []), key=lambda linha: linha.get("origem_indice") or 0)
        if len(obtidos) != len(lista_esperada):
            divergencias.append(f"{tabela} {origem_tabela}:{origem_id}: {len(obtidos)} linha(s) nova(s), esperado {len(lista_esperada)}")
            continue
        for valores, novo in zip(lista_esperada, obtidos, strict=True):
            for campo, valor in valores.items():
                if campo in IGNORADOS:
                    continue
                if campo in REFERENCIAS:
                    coluna = REFERENCIAS[campo][1]
                    obtido = None if novo[coluna] is None else por_referencia[campo].get(novo[coluna], ("?", novo[coluna]))
                    esperado_ref = tuple(valor) if valor and valor[1] is not None else None
                    if obtido != esperado_ref:
                        divergencias.append(f"{tabela} {origem_tabela}:{origem_id}.{coluna}: {obtido} != {esperado_ref}")
                elif _normalizar(novo.get(campo)) != _normalizar(valor):
                    divergencias.append(f"{tabela} {origem_tabela}:{origem_id}.{campo}: {novo.get(campo)!r} != {valor!r}")
    return divergencias


def tipos_de_documento(db: Session, lado: Lado, tenant_id: str, origem_processo: str) -> dict[int, set[str]]:
    """processo (id de origem) → tipos de documento, lido das tabelas novas."""
    processos, documentos = TABELAS["processo"], TABELAS["documento"]
    consulta = (select(processos.c.origem_id, documentos.c.tipo_documento)
                .join(processos, documentos.c.processo_id == processos.c.id)
                .where(documentos.c.lado == lado.value, processos.c.lado == lado.value, documentos.c.tenant_id == tenant_id,
                       processos.c.origem_tabela == origem_processo))
    resultado: dict[int, set[str]] = {}
    for origem_id, tipo in db.execute(consulta):
        resultado.setdefault(origem_id, set()).add(tipo)
    return resultado


def verificar(divergencias: list[str], contexto: str) -> None:
    if not divergencias:
        return
    if modo_leitura_dupla() == "ESTRITA":
        raise DivergenciaSourcing(f"{contexto}: " + "; ".join(divergencias[:10]))
    for divergencia in divergencias[:20]:
        logger.warning("SOURCING_DIVERGENCIA %s %s", contexto, divergencia)
