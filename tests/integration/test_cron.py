import pytest

from app.core.config import settings

SEGREDO = "segredo-de-teste-super-secreto"


@pytest.fixture()
def com_segredo_cron(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "cron_secret", SEGREDO)


def test_processar_envios_sem_segredo_configurado_recusa(client):
    """cron_secret vazio nunca autoriza, mesmo sem header (Onda I)."""
    resposta = client.post("/api/v1/cron/processar-envios")
    assert resposta.status_code == 403


def test_processar_envios_com_segredo_errado_recusa(client, com_segredo_cron):
    resposta = client.post("/api/v1/cron/processar-envios", headers={"X-Cron-Secret": "errado"})
    assert resposta.status_code == 403


def test_processar_envios_sem_header_recusa(client, com_segredo_cron):
    resposta = client.post("/api/v1/cron/processar-envios")
    assert resposta.status_code == 403


def test_processar_envios_com_segredo_certo_processa_todos_os_tenants(client, com_segredo_cron):
    resposta = client.post("/api/v1/cron/processar-envios", headers={"X-Cron-Secret": SEGREDO})

    assert resposta.status_code == 200
    corpo = resposta.json()
    assert "totais" in corpo
    assert set(corpo["totais"]) == {
        "enviadas",
        "falhas",
        "adiadas",
        "tarefas_linkedin_criadas",
        "descartadas_email_invalido",
    }
    assert isinstance(corpo["por_tenant"], dict)
