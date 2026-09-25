"""Observabilidade de requisição (Fase 3, Master Prompt §76).

- Correlation ID: aceita `X-Request-ID` do cliente (se for um valor
  seguro) ou gera um UUID; devolve no header da resposta; fica numa
  `ContextVar` para logs e para o `correlation_id` dos eventos de domínio.
- Log de acesso estruturado por requisição: método, rota, status,
  latência e correlation id. Nunca loga corpo, query string ou headers
  (podem conter PII ou segredo).
"""

import logging
import re
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

CABECALHO = "X-Request-ID"
_ID_SEGURO = re.compile(r"^[A-Za-z0-9._-]{8,128}$")

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)

logger_acesso = logging.getLogger("b2bon.acesso")


def correlation_id_atual() -> str | None:
    return _correlation_id.get()


class FiltroCorrelationId(logging.Filter):
    """Anexa `correlation_id` a todo registro de log."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.correlation_id = _correlation_id.get() or "-"
        return True


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        recebido = request.headers.get(CABECALHO)
        correlation_id = recebido if recebido and _ID_SEGURO.match(recebido) else uuid.uuid4().hex
        token = _correlation_id.set(correlation_id)
        inicio = time.monotonic()
        status = 500
        try:
            resposta = await call_next(request)
            status = resposta.status_code
            resposta.headers[CABECALHO] = correlation_id
            return resposta
        finally:
            latencia_ms = int((time.monotonic() - inicio) * 1000)
            logger_acesso.info(
                "method=%s path=%s status=%s latency_ms=%s request_id=%s",
                request.method, request.url.path, status, latencia_ms, correlation_id,
            )
            _correlation_id.reset(token)
