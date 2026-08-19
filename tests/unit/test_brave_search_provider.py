import httpx
import pytest

from app.core.config import settings
from app.providers.web_search.brave import BraveSearchProvider


class _RespostaFalsa:
    def __init__(self, corpo: dict, status_code: int = 200) -> None:
        self._corpo = corpo
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("erro", request=None, response=self)

    def json(self) -> dict:
        return self._corpo


def test_busca_com_sucesso_mapeia_resultados(monkeypatch: pytest.MonkeyPatch) -> None:
    def _get_falso(url: str, params: dict, headers: dict, timeout: float) -> _RespostaFalsa:
        assert headers["X-Subscription-Token"] == "chave-teste"
        return _RespostaFalsa(
            {"web": {"results": [{"title": "Alpha Tech", "url": "https://alphatech.com.br", "description": "x"}]}}
        )

    monkeypatch.setattr(settings, "brave_search_api_key", "chave-teste")
    monkeypatch.setattr(httpx, "get", _get_falso)

    resultados = BraveSearchProvider().buscar("Alpha Tech site oficial")

    assert len(resultados) == 1
    assert resultados[0].url == "https://alphatech.com.br"


def test_chave_invalida_ou_sem_credito_nao_derruba_a_chamada(monkeypatch: pytest.MonkeyPatch) -> None:
    """Raio-X de produção real: 401/402/429 da Brave virava exceção não
    tratada (500 cru, sem cabeçalhos de CORS — aparecia pro usuário como
    erro de CORS). Sem resultado, não é motivo pra derrubar a chamada."""

    def _get_falso(url: str, params: dict, headers: dict, timeout: float) -> _RespostaFalsa:
        return _RespostaFalsa({"error": "unauthorized"}, status_code=401)

    monkeypatch.setattr(settings, "brave_search_api_key", "chave-invalida")
    monkeypatch.setattr(httpx, "get", _get_falso)

    resultados = BraveSearchProvider().buscar("Alpha Tech site oficial")

    assert resultados == []


def test_timeout_nao_derruba_a_chamada(monkeypatch: pytest.MonkeyPatch) -> None:
    def _get_falso(url: str, params: dict, headers: dict, timeout: float):
        raise httpx.TimeoutException("timeout")

    monkeypatch.setattr(settings, "brave_search_api_key", "chave-teste")
    monkeypatch.setattr(httpx, "get", _get_falso)

    resultados = BraveSearchProvider().buscar("Alpha Tech site oficial")

    assert resultados == []
