import logging

from app.core.observability import FiltroCorrelationId


def configure_logging() -> None:
    # Sem dados pessoais em logs de aplicação — DoD do backlog (E9).
    # `correlation_id` (Fase 3) liga cada linha ao request de origem.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s [%(correlation_id)s] %(message)s",
    )
    for handler in logging.getLogger().handlers:
        handler.addFilter(FiltroCorrelationId())
