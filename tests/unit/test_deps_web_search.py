import pytest

from app.api.deps import get_web_search_provider
from app.core.config import settings
from app.providers.web_search.base import WebSearchProvider
from app.providers.web_search.brave import BraveSearchProvider
from app.providers.web_search.desativado import WebSearchDesativadoProvider
from app.providers.web_search.stub import StubWebSearchProvider


def test_com_chave_configurada_usa_brave(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "brave_search_api_key", "chave-real")

    provider = get_web_search_provider()

    assert isinstance(provider, BraveSearchProvider)


def test_sem_chave_em_producao_nao_fabrica_dominio_falso(monkeypatch: pytest.MonkeyPatch) -> None:
    """Trava a correção do raio-X: StubWebSearchProvider fabrica um domínio
    plausível a partir da query — vazando pra produção sem chave real, isso
    salvava um site inexistente na conta em vez de simplesmente não achar
    nada (ver WebSearchDesativadoProvider)."""
    monkeypatch.setattr(settings, "brave_search_api_key", "")
    monkeypatch.setattr(settings, "database_url", "postgresql://user:pass@host/db")

    provider = get_web_search_provider()

    assert isinstance(provider, WebSearchDesativadoProvider)
    assert provider.buscar("Empresa Teste site oficial") == []


def test_sem_chave_fora_de_producao_usa_stub_de_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "brave_search_api_key", "")
    monkeypatch.setattr(settings, "database_url", "sqlite:///./predator.db")

    provider = get_web_search_provider()

    assert isinstance(provider, StubWebSearchProvider)


def test_desativado_provider_implementa_a_interface() -> None:
    provider: WebSearchProvider = WebSearchDesativadoProvider()
    assert provider.buscar("qualquer coisa") == []
