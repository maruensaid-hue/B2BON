"""Sentry: rotas de máquina (cron, health) não consomem cota de transações; o resto mantém a taxa de 10%."""

import pytest

from app.core.observability import TAXA_TRACES, amostrar_traces


@pytest.mark.parametrize("caminho", ["/health", "/api/v1/cron/processar-envios", "/api/v1/cron/processar-eventos", "/api/v1/cron/podar-historicos"])
def test_rotas_de_maquina_nao_sao_amostradas(caminho):
    assert amostrar_traces({"asgi_scope": {"path": caminho}}) == 0.0


@pytest.mark.parametrize("caminho", ["/api/v1/crm/negocios", "/api/v1/auth/login", "/api/v1/leads/contas", "/healthz-outro", "/api/v1/cronograma"])
def test_rotas_de_usuario_mantem_a_taxa(caminho):
    assert amostrar_traces({"asgi_scope": {"path": caminho}}) == TAXA_TRACES


def test_contexto_sem_caminho_usa_a_taxa_padrao():
    assert amostrar_traces({}) == TAXA_TRACES
