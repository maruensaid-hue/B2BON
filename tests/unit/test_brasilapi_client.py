import httpx
import pytest

from app.integrations.brasilapi_client import consultar_cnpj_brasilapi


class _RespostaFalsa:
    def __init__(self, json_data: dict) -> None:
        self._json_data = json_data

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._json_data


def test_cnpj_formatado_e_normalizado_antes_da_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Raio-X 2026-09-16: um CNPJ salvo com pontuação ("14.568.725/0001-95")
    quebrava a própria URL da BrasilAPI — a barra virava separador de
    caminho e a API respondia 404 mesmo pro CNPJ certo (bug real
    reportado em produção)."""
    urls_chamadas = []

    def get_falso(url: str, **kwargs) -> _RespostaFalsa:
        urls_chamadas.append(url)
        return _RespostaFalsa({"email": "contato@empresa.com.br"})

    monkeypatch.setattr(httpx, "get", get_falso)

    consultar_cnpj_brasilapi("14.568.725/0001-95")

    assert urls_chamadas == ["https://brasilapi.com.br/api/cnpj/v1/14568725000195"]


def test_cnpj_ja_limpo_continua_funcionando(monkeypatch: pytest.MonkeyPatch) -> None:
    urls_chamadas = []
    monkeypatch.setattr(httpx, "get", lambda url, **kwargs: urls_chamadas.append(url) or _RespostaFalsa({}))

    consultar_cnpj_brasilapi("14568725000195")

    assert urls_chamadas == ["https://brasilapi.com.br/api/cnpj/v1/14568725000195"]
