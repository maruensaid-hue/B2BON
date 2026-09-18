from fastapi.testclient import TestClient

from app import main as app_main


def test_health(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_com_banco_fora_do_ar_retorna_503(client: TestClient, monkeypatch) -> None:
    """Fase 7C, hardening — antes /health respondia "ok" mesmo com o
    banco derrubado, já que nunca chegava a consultá-lo de verdade."""

    class _EngineQueQuebra:
        def connect(self):
            raise ConnectionError("banco fora do ar")

    monkeypatch.setattr(app_main, "engine", _EngineQueQuebra())

    response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "erro", "database": "erro"}
