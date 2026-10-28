"""O log de acesso não guarda credenciais que viajam no endereço (auditoria de segurança A09)."""

import logging

import pytest

from app.core.observability import caminho_para_log


@pytest.mark.parametrize(
    ("caminho", "esperado"),
    [
        ("/api/v1/hub-integracoes/webhook/AbCdEf123456", "/api/v1/hub-integracoes/webhook/***"),
        ("/api/v1/webhooks/email/aberto/c1:2:assinatura.png", "/api/v1/webhooks/email/aberto/***"),
        ("/api/v1/nps/responder/token-secreto", "/api/v1/nps/responder/***"),
        ("/api/v1/opt-out/campanha/token-secreto", "/api/v1/opt-out/campanha/***"),
        ("/api/v1/reunioes/reagendar/token-secreto", "/api/v1/reunioes/reagendar/***"),
        ("/api/v1/portal-fornecedor/link-secreto/propostas", "/api/v1/portal-fornecedor/***/propostas"),
        ("/api/v1/crm/negocios/5", "/api/v1/crm/negocios/5"),
        ("/health", "/health"),
    ],
)
def test_caminho_para_log_remove_o_segredo(caminho: str, esperado: str) -> None:
    assert caminho_para_log(caminho) == esperado


def test_log_de_acesso_nao_contem_o_token_do_webhook(client) -> None:
    # Handler próprio no logger de acesso: independe de propagação/nível que outros testes possam ter alterado no logging global.
    registros: list[str] = []

    class Coletor(logging.Handler):
        def emit(self, registro: logging.LogRecord) -> None:
            registros.append(registro.getMessage())

    coletor = Coletor(level=logging.DEBUG)
    logger = logging.getLogger("b2bon.acesso")
    nivel_anterior, desativado_anterior = logger.level, logger.disabled
    logger.addHandler(coletor)
    logger.setLevel(logging.INFO)
    logger.disabled = False
    try:
        client.post("/api/v1/hub-integracoes/webhook/TOKEN-QUE-NAO-PODE-VAZAR")
    finally:
        logger.removeHandler(coletor)
        logger.setLevel(nivel_anterior)
        logger.disabled = desativado_anterior
    texto = " ".join(registros)
    assert "hub-integracoes/webhook/***" in texto
    assert "TOKEN-QUE-NAO-PODE-VAZAR" not in texto
