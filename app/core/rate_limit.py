import logging
import secrets
import time
from collections import defaultdict
from threading import Lock

from redis import Redis
from redis.exceptions import RedisError

from fastapi import Request

from app.core.config import settings
from app.services.errors import LimiteDeTaxaExcedido

logger = logging.getLogger(__name__)


class LimitadorEmMemoria:
    """Usa Redis compartilhado quando REDIS_URL está configurado; memória é fallback de desenvolvimento legado."""

    def __init__(self) -> None:
        self._tentativas: dict[str, list[float]] = defaultdict(list)
        self._lock = Lock()
        self._redis: Redis | None = None

    def checar(self, chave: str, max_tentativas: int, janela_segundos: int) -> None:
        if settings.redis_url:
            self._checar_redis(chave, max_tentativas, janela_segundos)
            return
        agora = time.monotonic()
        with self._lock:
            tentativas = self._tentativas[chave]
            limite_inferior = agora - janela_segundos
            tentativas[:] = [instante for instante in tentativas if instante > limite_inferior]
            if len(tentativas) >= max_tentativas:
                raise LimiteDeTaxaExcedido("Muitas tentativas. Aguarde alguns minutos antes de tentar novamente.")
            tentativas.append(agora)

    def _checar_redis(self, chave: str, max_tentativas: int, janela_segundos: int) -> None:
        """Janela deslizante atômica, compartilhada por todas as instâncias da API."""
        if self._redis is None:
            self._redis = Redis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2)
        script = """
        local key = KEYS[1]
        local now = tonumber(ARGV[1])
        local cutoff = now - tonumber(ARGV[2])
        local limit = tonumber(ARGV[3])
        local member = ARGV[4]
        redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)
        local count = redis.call('ZCARD', key)
        if count >= limit then
          redis.call('EXPIRE', key, tonumber(ARGV[2]) + 5)
          return 0
        end
        redis.call('ZADD', key, now, member)
        redis.call('EXPIRE', key, tonumber(ARGV[2]) + 5)
        return 1
        """
        try:
            permitido = self._redis.eval(
                script, 1, "b2bon:ratelimit:" + chave, time.time(), janela_segundos,
                max_tentativas, secrets.token_hex(16),
            )
        except RedisError as erro:
            logger.error("Rate limit Redis indisponível; tentativa negada", exc_info=True)
            raise LimiteDeTaxaExcedido("Proteção temporariamente indisponível. Tente novamente.") from erro
        if not permitido:
            raise LimiteDeTaxaExcedido("Muitas tentativas. Aguarde alguns minutos antes de tentar novamente.")

    def resetar(self) -> None:
        """Só para teste — evita que o estado de um teste vaze pro próximo
        (a suíte inteira roda no mesmo processo)."""
        with self._lock:
            self._tentativas.clear()


limitador_auth = LimitadorEmMemoria()

# Bucket separado do de auth (Fase 2 da hierarquia, raio-X) — tráfego de
# parceiro (chave de API) não deve competir por cota com tentativas de
# login/registro, são naturezas de abuso bem diferentes.
limitador_parceiros = LimitadorEmMemoria()

# Bucket separado pras rotas que chamam LLM (Fase 7A, hardening) — cada
# chamada custa dinheiro de verdade; sem isto, nada limitava quantas
# vezes um tenant (autenticado, não anônimo) podia disparar IA.
limitador_ia = LimitadorEmMemoria()

# API de produto por chave de tenant (Fase 3) — bucket próprio por chave.
limitador_api = LimitadorEmMemoria()

# Portal do fornecedor por link (Phase F) — rota sem login: bucket por IP.
limitador_portal = LimitadorEmMemoria()


def limitar_por_ip(max_tentativas: int = 5, janela_segundos: int = 300):
    """Dependency factory — protege rotas públicas de autenticação contra
    força bruta (login) e criação em massa (registro), sem exigir
    infraestrutura nova."""

    def _dependencia(request: Request) -> None:
        ip = request.client.host if request.client else "desconhecido"
        limitador_auth.checar(f"{request.url.path}:{ip}", max_tentativas, janela_segundos)

    return _dependencia


# Demonstração pública (D-083): por cliente real e um teto global por hora.
limitador_demo = LimitadorEmMemoria()


def _ip_cliente(request: Request) -> str:
    """Atrás do proxy do Render, `client.host` é o proxy; o IP real é o último item que o próprio proxy acrescenta ao
    X-Forwarded-For (o primeiro pode ser forjado pelo cliente, o último não)."""
    encaminhado = request.headers.get("x-forwarded-for", "")
    ultimo = encaminhado.split(",")[-1].strip() if encaminhado else ""
    return ultimo or (request.client.host if request.client else "desconhecido")


def limitar_demonstracao(por_ip_hora: int, global_hora: int):
    def _dependencia(request: Request) -> None:
        limitador_demo.checar("global", global_hora, 3600)
        limitador_demo.checar(f"ip:{_ip_cliente(request)}", por_ip_hora, 3600)

    return _dependencia
