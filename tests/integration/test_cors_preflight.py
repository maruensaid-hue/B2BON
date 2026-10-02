"""Checagem prévia de CORS (OPTIONS) — caso real 2026-10-02: o /demo não abria no Samsung Internet porque o navegador
pedia `Access-Control-Request-Private-Network` e o Starlette recusava com 400."""

import logging

ORIGEM = "http://localhost:5173"  # padrão de `cors_origins` nos testes


def _preflight(client, origem: str, extra: dict | None = None):
    return client.options("/api/v1/auth/demonstracao", headers={
        "Origin": origem, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "authorization,content-type", **(extra or {})})


def test_aceita_pedido_de_rede_privada_da_origem_permitida(client):
    resposta = _preflight(client, ORIGEM, {"Access-Control-Request-Private-Network": "true"})
    assert resposta.status_code == 200
    assert resposta.headers["access-control-allow-private-network"] == "true"
    assert resposta.headers["access-control-allow-origin"] == ORIGEM


def test_origem_desconhecida_continua_recusada_e_registrada(client, caplog):
    with caplog.at_level(logging.WARNING, logger="b2bon.cors"):
        resposta = _preflight(client, "https://site-qualquer.example", {"Access-Control-Request-Private-Network": "true"})
    assert resposta.status_code == 400
    assert "access-control-allow-origin" not in resposta.headers
    assert "site-qualquer.example" in caplog.text and "origin" in caplog.text


def test_site_proprio_do_render_e_aceito(client):
    """Produção 2026-10-02: o botão DEMO leva a https://b2bon.onrender.com/demo, e essa origem não estava em
    CORS_ORIGINS ("Disallowed CORS origin") — a demonstração não abria em nenhum navegador."""
    resposta = _preflight(client, "https://b2bon.onrender.com")
    assert resposta.status_code == 200
    assert resposta.headers["access-control-allow-origin"] == "https://b2bon.onrender.com"


def test_origens_somam_painel_e_proprias_sem_repetir(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "cors_origins", '["https://b2bon.maruen-said.workers.dev", "https://b2bon.onrender.com/"]')
    assert settings.origens_cors == ["https://b2bon.maruen-said.workers.dev", "https://b2bon.onrender.com"]
    monkeypatch.setattr(settings, "cors_origins", "https://a.example, https://b.example")
    monkeypatch.setattr(settings, "cors_origins_proprias", "")
    assert settings.origens_cors == ["https://a.example", "https://b.example"]
