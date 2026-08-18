import httpx
import pytest

from app.providers.contact_enrichment.base import FiltroContatos
from app.providers.contact_enrichment.lusha import LushaContactEnrichmentProvider


class _RespostaFalsa:
    def __init__(self, corpo: dict, status_code: int = 200) -> None:
        self._corpo = corpo
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("erro", request=None, response=self)

    def json(self) -> dict:
        return self._corpo


def test_busca_encadeia_search_e_enrich_e_mapeia_campos(monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas = []

    def _post_falso(url: str, json: dict, headers: dict, timeout: float) -> _RespostaFalsa:
        chamadas.append((url, json, headers))
        if url.endswith("/prospecting/contact/search"):
            assert headers["api_key"] == "chave-teste"
            assert json["filters"]["companies"]["include"]["domains"] == ["empresateste.com.br"]
            assert json["filters"]["contacts"]["include"]["jobTitles"] == ["CEO", "Diretor"]
            return _RespostaFalsa(
                {"requestId": "req-1", "contacts": [{"contactId": "c1"}, {"contactId": "c2"}]}
            )
        assert url.endswith("/prospecting/contact/enrich")
        assert json == {"requestId": "req-1", "contactIds": ["c1", "c2"]}
        return _RespostaFalsa(
            {
                "contacts": [
                    {
                        "fullName": "Ana Souza",
                        "jobTitle": "CEO",
                        "emailAddresses": [{"email": "ana@empresateste.com.br"}],
                        "phoneNumbers": [{"phoneNumber": "+5511988887777"}],
                        "linkedinUrl": "https://linkedin.com/in/ana-souza",
                    },
                    {
                        "firstName": "Carlos",
                        "lastName": "Lima",
                        "jobTitle": "Diretor",
                        "emailAddresses": [],
                        "phoneNumbers": [],
                    },
                ]
            }
        )

    monkeypatch.setattr(httpx, "post", _post_falso)

    provider = LushaContactEnrichmentProvider(api_key="chave-teste")
    resultado = provider.buscar_contatos(
        FiltroContatos(nome_empresa="Empresa Teste", dominio="empresateste.com.br", cargos_alvo=["CEO", "Diretor"])
    )

    assert len(chamadas) == 2
    assert len(resultado) == 2
    assert resultado[0].nome == "Ana Souza"
    assert resultado[0].email == "ana@empresateste.com.br"
    assert resultado[0].telefone == "+5511988887777"
    assert resultado[0].linkedin_url == "https://linkedin.com/in/ana-souza"
    assert resultado[0].fonte == "lusha"
    assert resultado[1].nome == "Carlos Lima"
    assert resultado[1].email is None
    assert resultado[1].telefone is None


def test_busca_sem_dominio_filtra_por_nome_da_empresa(monkeypatch: pytest.MonkeyPatch) -> None:
    def _post_falso(url: str, json: dict, headers: dict, timeout: float) -> _RespostaFalsa:
        if url.endswith("/search"):
            assert json["filters"]["companies"]["include"]["names"] == ["Empresa Sem Dominio"]
            return _RespostaFalsa({"requestId": "req-1", "contacts": []})
        return _RespostaFalsa({"contacts": []})

    monkeypatch.setattr(httpx, "post", _post_falso)

    provider = LushaContactEnrichmentProvider(api_key="chave-teste")
    resultado = provider.buscar_contatos(FiltroContatos(nome_empresa="Empresa Sem Dominio"))

    assert resultado == []


def test_search_sem_resultados_nao_chama_enrich(monkeypatch: pytest.MonkeyPatch) -> None:
    chamadas = []

    def _post_falso(url: str, json: dict, headers: dict, timeout: float) -> _RespostaFalsa:
        chamadas.append(url)
        return _RespostaFalsa({"requestId": "req-1", "contacts": []})

    monkeypatch.setattr(httpx, "post", _post_falso)

    provider = LushaContactEnrichmentProvider(api_key="chave-teste")
    resultado = provider.buscar_contatos(FiltroContatos(nome_empresa="Empresa Teste"))

    assert resultado == []
    assert len(chamadas) == 1


def test_erro_http_na_busca_retorna_lista_vazia(monkeypatch: pytest.MonkeyPatch) -> None:
    def _post_falso(url: str, json: dict, headers: dict, timeout: float) -> _RespostaFalsa:
        return _RespostaFalsa({"erro": "chave invalida"}, status_code=401)

    monkeypatch.setattr(httpx, "post", _post_falso)

    provider = LushaContactEnrichmentProvider(api_key="chave-invalida")
    resultado = provider.buscar_contatos(FiltroContatos(nome_empresa="Empresa Teste"))

    assert resultado == []


def test_erro_http_no_enrich_retorna_lista_vazia(monkeypatch: pytest.MonkeyPatch) -> None:
    def _post_falso(url: str, json: dict, headers: dict, timeout: float) -> _RespostaFalsa:
        if url.endswith("/search"):
            return _RespostaFalsa({"requestId": "req-1", "contacts": [{"contactId": "c1"}]})
        return _RespostaFalsa({"erro": "falhou"}, status_code=500)

    monkeypatch.setattr(httpx, "post", _post_falso)

    provider = LushaContactEnrichmentProvider(api_key="chave-teste")
    resultado = provider.buscar_contatos(FiltroContatos(nome_empresa="Empresa Teste"))

    assert resultado == []
