import time
from threading import Lock

from app.integrations.central_negocios_client import Mercado, MercadoClient, Noticia, NoticiasClient

# Página pública sem login (Central de Negócios) — cache por processo evita
# bater nas APIs externas (Yahoo Finance, AwesomeAPI, RSS dos portais) a
# cada carregamento de página; mesmo raciocínio de janela em memória já
# usado em `LimitadorEmMemoria` (app/core/rate_limit.py), sem precisar de
# backend compartilhado enquanto a API roda numa única instância.
_TTL_SEGUNDOS = 900

_lock = Lock()
_mercado_cache: Mercado | None = None
_mercado_cache_em: float = 0.0
_noticias_cache: list[Noticia] | None = None
_noticias_cache_em: float = 0.0


def obter_mercado(mercado_client: MercadoClient) -> Mercado:
    global _mercado_cache, _mercado_cache_em
    agora = time.monotonic()
    with _lock:
        if _mercado_cache is not None and (agora - _mercado_cache_em) < _TTL_SEGUNDOS:
            return _mercado_cache
        cache_anterior = _mercado_cache

    dados = mercado_client()

    # Fallback "stale-enquanto-revalida": uma fonte externa rate-limitada
    # (ex.: AwesomeAPI devolvendo 429, achado real em produção 2026-09-21)
    # não pode apagar um dado bom que já tínhamos — melhor mostrar a
    # última cotação real conhecida do que "indisponível" por 15min só
    # porque a busca mais recente falhou. Cada lista (índices/câmbio) cai
    # pro valor anterior independentemente, só quando a nova vier vazia.
    if cache_anterior:
        if not dados["indices"] and cache_anterior["indices"]:
            dados["indices"] = cache_anterior["indices"]
        if not dados["cambio"] and cache_anterior["cambio"]:
            dados["cambio"] = cache_anterior["cambio"]

    with _lock:
        _mercado_cache = dados
        _mercado_cache_em = agora
    return dados


def obter_noticias(noticias_client: NoticiasClient) -> list[Noticia]:
    global _noticias_cache, _noticias_cache_em
    agora = time.monotonic()
    with _lock:
        if _noticias_cache is not None and (agora - _noticias_cache_em) < _TTL_SEGUNDOS:
            return _noticias_cache
        cache_anterior = _noticias_cache

    dados = noticias_client()
    # Mesmo fallback stale-enquanto-revalida de `obter_mercado` acima.
    if not dados and cache_anterior:
        dados = cache_anterior

    with _lock:
        _noticias_cache = dados
        _noticias_cache_em = agora
    return dados


def resetar_cache() -> None:
    """Só para teste — evita que o cache de um teste vaze pro próximo (a
    suíte inteira roda no mesmo processo)."""
    global _mercado_cache, _mercado_cache_em, _noticias_cache, _noticias_cache_em
    with _lock:
        _mercado_cache = None
        _mercado_cache_em = 0.0
        _noticias_cache = None
        _noticias_cache_em = 0.0
