import pytest

from app.api.deps import get_contact_enrichment_provider
from app.core.config import settings
from app.providers.contact_enrichment.base import FiltroContatos
from app.providers.contact_enrichment.desativado import ContactEnrichmentDesativadoProvider
from app.providers.contact_enrichment.lusha import LushaContactEnrichmentProvider
from app.providers.contact_enrichment.stub import StubContactEnrichmentProvider


def test_com_chave_configurada_usa_lusha(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "contact_enrichment_api_key", "chave-real")

    provider = get_contact_enrichment_provider()

    assert isinstance(provider, LushaContactEnrichmentProvider)


def test_sem_chave_em_producao_nao_usa_dados_ficticios(monkeypatch: pytest.MonkeyPatch) -> None:
    """Trava a correção do raio-X: `mapear_decisores` chama `buscar_contatos`
    sem nenhuma trava — sem isto, o stub de contatos fixos vazaria pra
    produção e criaria decisores fantasma reais no CRM."""
    monkeypatch.setattr(settings, "contact_enrichment_api_key", "")
    monkeypatch.setattr(settings, "database_url", "postgresql://user:pass@host/db")

    provider = get_contact_enrichment_provider()

    assert isinstance(provider, ContactEnrichmentDesativadoProvider)
    assert provider.buscar_contatos(FiltroContatos(nome_empresa="Empresa Teste")) == []


def test_sem_chave_fora_de_producao_usa_stub_de_dev(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "contact_enrichment_api_key", "")
    monkeypatch.setattr(settings, "database_url", "sqlite:///./predator.db")

    provider = get_contact_enrichment_provider()

    assert isinstance(provider, StubContactEnrichmentProvider)
