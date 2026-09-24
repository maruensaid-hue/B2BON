import logging
import time
from threading import Lock

from sqlalchemy.orm import Session

from app.integrations.central_negocios_client import Mercado, MercadoClient, Noticia, NoticiasClient
from app.models.cache_mercado_externo import CacheMercadoExterno

logger = logging.getLogger(__name__)

_CHAVE_CACHE_MERCADO = "mercado"

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


def obter_mercado(mercado_client: MercadoClient, db: Session) -> Mercado:
    global _mercado_cache, _mercado_cache_em
    agora = time.monotonic()
    with _lock:
        if _mercado_cache is not None and (agora - _mercado_cache_em) < _TTL_SEGUNDOS:
            return _mercado_cache
        cache_anterior = _mercado_cache

    dados = mercado_client()

    # Raio-X 2026-09-24: cold start do plano free do Render zera o cache
    # em memória (`cache_anterior=None`) — se coincidir com a AwesomeAPI
    # bloqueada bem na primeira chamada, não existia nada pro fallback
    # stale usar, e o câmbio ficava "indisponível" pra sempre. Carrega o
    # último valor bom persistido no banco pra preencher esse vazio.
    if cache_anterior is None:
        cache_anterior = _carregar_cache_persistido(db)

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

    if dados["indices"] or dados["cambio"]:
        _persistir_cache(db, dados)
    return dados


def _carregar_cache_persistido(db: Session) -> Mercado | None:
    try:
        linha = db.get(CacheMercadoExterno, _CHAVE_CACHE_MERCADO)
    except Exception:
        logger.warning("Não foi possível ler o cache persistido de mercado", exc_info=True)
        return None
    return linha.valor if linha else None  # type: ignore[return-value]


def _persistir_cache(db: Session, dados: Mercado) -> None:
    """Best-effort — uma falha aqui nunca pode derrubar a resposta
    pública (a leitura/gravação em si não é o que o usuário pediu)."""
    try:
        linha = db.get(CacheMercadoExterno, _CHAVE_CACHE_MERCADO)
        if linha is None:
            db.add(CacheMercadoExterno(chave=_CHAVE_CACHE_MERCADO, valor=dados))
        else:
            linha.valor = dados
        db.commit()
    except Exception:
        logger.warning("Não foi possível persistir o cache de mercado", exc_info=True)
        db.rollback()


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
