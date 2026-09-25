"""Observabilidade e cache (Fase 17)."""

import logging

from app.core.config import settings


def test_requisicao_lenta_vira_warning_com_marca_slow(client, monkeypatch, caplog):
    monkeypatch.setattr(settings, "log_requisicao_lenta_ms", 0)
    with caplog.at_level(logging.INFO, logger="b2bon.acesso"):
        client.get("/api/v1/catalogo")
    registro = next(r for r in caplog.records if r.name == "b2bon.acesso" and "/api/v1/catalogo" in r.getMessage())
    assert registro.levelno == logging.WARNING and "slow=1" in registro.getMessage()


def test_requisicao_normal_continua_info(client, caplog):
    with caplog.at_level(logging.INFO, logger="b2bon.acesso"):
        client.get("/health")
    registro = next(r for r in caplog.records if r.name == "b2bon.acesso" and "/health" in r.getMessage())
    assert registro.levelno == logging.INFO and "slow=1" not in registro.getMessage()


def test_catalogo_publico_tem_cache_curto_e_assinatura_nao(client):
    assert client.get("/api/v1/catalogo").headers["Cache-Control"] == "public, max-age=300"
    assert "public" not in client.get("/api/v1/assinatura").headers.get("Cache-Control", "")
