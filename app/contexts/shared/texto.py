"""Texto determinístico e explicável — Shared Kernel (sem embeddings, D-017).

- Grounding: um trecho citado pela IA só vale se aparecer literalmente na
  fonte, ignorando caixa, acento, pontuação e espaços.
- Casamento por termos: tokens sem acento e sem stopwords, radical por
  prefixo de 6 letras ("licenças" e "licenciamento" casam). Dois textos
  casam quando dividem ao menos metade dos termos do menor deles; os
  termos em comum voltam junto para a evidência mostrar POR QUE casou.

Usado por Opportunity Intelligence (Fase 6) e Bid Intelligence (Fase 9).
"""

import re
import unicodedata


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", sem_acento.lower())).strip()


def contem_literal(fonte: str, trecho: str) -> bool:
    trecho_n = normalizar(trecho)
    return len(trecho_n) >= 8 and trecho_n in normalizar(fonte)


def localizar_pagina(paginas: list[str], trecho: str) -> int | None:
    """Página (1-based) onde o trecho aparece literalmente; None se em nenhuma
    (inclusive quando atravessa a quebra de página)."""
    for indice, pagina in enumerate(paginas, start=1):
        if contem_literal(pagina, trecho):
            return indice
    return None


_STOPWORDS = frozenset(
    """
    para como mais menos muito pouco sobre entre desde quando onde porque porque
    esta este isso isto essa esse estao estamos temos tenho fazer feito seria
    pela pelo pelas pelos numa num uma umas uns com sem das dos que qual quais
    cliente clientes empresa empresas precisa precisam precisamos necessidade
    querem quer queremos hoje ainda tambem nosso nossa nossos nossas deles delas
    """.split()
)
_RADICAL = 6


def termos(texto: str | None) -> set[str]:
    if not texto:
        return set()
    return {p[:_RADICAL] for p in normalizar(texto).split() if len(p) >= 4 and p not in _STOPWORDS}


def termos_em_comum(a: str | None, b: str | None) -> set[str]:
    ta, tb = termos(a), termos(b)
    comuns = ta & tb
    if not comuns or len(comuns) * 2 < min(len(ta), len(tb)):
        return set()
    return comuns
