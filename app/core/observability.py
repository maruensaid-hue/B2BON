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

from app.core.config import settings

CABECALHO = "X-Request-ID"
_ID_SEGURO = re.compile(r"^[A-Za-z0-9._-]{8,128}$")

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)

logger_acesso = logging.getLogger("b2bon.acesso")


# Rotas que carregam uma credencial ou um segredo no próprio endereço (token de webhook de CRM, link de NPS, de opt-out, de reagendamento, do pixel de abertura
# e do portal do fornecedor). O log guarda o endereço sem esse trecho: quem tem acesso aos logs não pode reaproveitar a credencial (auditoria de segurança A09).
_SEGREDOS_NO_CAMINHO = re.compile(
    r"(/hub-integracoes/webhook/|/nps/responder/|/opt-out/(?:email|campanha)/|/reunioes/reagendar/|/webhooks/email/aberto/|/portal-fornecedor/)[^/\s]+"
)


def caminho_para_log(caminho: str) -> str:
    """Endereço da requisição sem tokens/segredos, para ir ao log."""
    return _SEGREDOS_NO_CAMINHO.sub(r"\g<1>***", caminho)


TAXA_TRACES = 0.1
# Rotas de máquina: os crons (7 chamadas a cada 15 min) e o health check respondem pela maior parte do tráfego da API e não trazem informação de
# desempenho que um usuário perceba. Erros delas continuam sendo capturados (o amostrador só afeta transações de desempenho).
_CAMINHOS_SEM_TRACE = ("/api/v1/cron/", "/health")


def amostrar_traces(contexto_de_amostragem: dict) -> float:
    """`traces_sampler` do Sentry: 10% das requisições de usuário, 0% das rotas de máquina (poupa a cota de transações)."""
    escopo = contexto_de_amostragem.get("asgi_scope") or {}
    caminho = escopo.get("path") or (contexto_de_amostragem.get("wsgi_environ") or {}).get("PATH_INFO", "")
    if caminho == "/health" or caminho.startswith(_CAMINHOS_SEM_TRACE[0]):
        return 0.0
    return TAXA_TRACES


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
            # Fase 17: requisição lenta sobe para WARNING (alerta sem precisar varrer INFO).
            lenta = latencia_ms >= settings.log_requisicao_lenta_ms
            logger_acesso.log(
                logging.WARNING if lenta else logging.INFO,
                "method=%s path=%s status=%s latency_ms=%s request_id=%s%s",
                request.method, caminho_para_log(request.url.path), status, latencia_ms, correlation_id, " slow=1" if lenta else "",
            )
            _correlation_id.reset(token)
