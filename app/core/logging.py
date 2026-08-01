import logging


def configure_logging() -> None:
    # Sem dados pessoais em logs de aplicação — DoD do backlog (E9).
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
