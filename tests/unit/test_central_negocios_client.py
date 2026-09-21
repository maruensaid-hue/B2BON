import httpx
import pytest

from app.integrations import central_negocios_client


class _RespostaFalsa:
    def __init__(self, json_data: dict | None = None, text: str | None = None) -> None:
        self._json_data = json_data
        self.text = text or ""

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._json_data or {}


def test_buscar_indice_extrai_pontos_variacao_e_serie(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import UTC, datetime

    instante = datetime(2026, 9, 21, 14, 0, tzinfo=UTC).timestamp()
    resposta_yahoo = {
        "chart": {
            "result": [
                {
                    "meta": {"regularMarketPrice": 130123.456, "regularMarketChangePercent": 1.2345},
                    "timestamp": [instante, instante + 86400],
                    "indicators": {"quote": [{"close": [129000.111, None]}]},
                }
            ]
        }
    }
    monkeypatch.setattr(httpx, "get", lambda url, **kwargs: _RespostaFalsa(resposta_yahoo))

    resultado = central_negocios_client._buscar_indice("^BVSP", "Ibovespa")

    assert resultado["nome"] == "Ibovespa"
    assert resultado["pontos"] == 130123.46
    assert resultado["variacao_pct"] == 1.23
    # `None` no ponto seguinte (pregão sem fechamento) é pulado, não quebra.
    assert resultado["serie"] == [{"data": "21/09", "valor": 129000.11}]


def test_buscar_indice_falha_de_rede_nao_lanca(monkeypatch: pytest.MonkeyPatch) -> None:
    def get_falso(url: str, **kwargs):
        raise httpx.ConnectError("sem rede")

    monkeypatch.setattr(httpx, "get", get_falso)

    assert central_negocios_client._buscar_indice("^BVSP", "Ibovespa") is None


def test_buscar_indice_resposta_mal_formada_nao_lanca(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "get", lambda url, **kwargs: _RespostaFalsa({"chart": {"result": []}}))

    assert central_negocios_client._buscar_indice("^BVSP", "Ibovespa") is None


def test_buscar_indices_falha_de_um_indice_nao_derruba_os_demais(monkeypatch: pytest.MonkeyPatch) -> None:
    resposta_ok = {
        "chart": {
            "result": [
                {
                    "meta": {"regularMarketPrice": 100.0, "regularMarketChangePercent": 1.0},
                    "timestamp": [],
                    "indicators": {"quote": [{"close": []}]},
                }
            ]
        }
    }

    def get_falso(url: str, **kwargs):
        if "BVSP" in url:
            raise httpx.ConnectError("fora do ar")
        return _RespostaFalsa(resposta_ok)

    monkeypatch.setattr(httpx, "get", get_falso)

    indices = central_negocios_client.buscar_indices()

    nomes = [indice["nome"] for indice in indices]
    assert "Ibovespa" not in nomes
    assert "Dow Jones (Nova Iorque)" in nomes
    assert "Nasdaq" in nomes


def test_buscar_cambio_extrai_todas_as_moedas_cripto_e_ouro(monkeypatch: pytest.MonkeyPatch) -> None:
    resposta_awesome = {
        "USDBRL": {"bid": "5.1104", "pctChange": "-0.657048"},
        "EURBRL": {"bid": "5.8609", "pctChange": "-0.840865"},
        "GBPBRL": {"bid": "6.8306", "pctChange": "-0.682917"},
        "JPYBRL": {"bid": "0.032454", "pctChange": "-0.844001"},
        "BTCBRL": {"bid": "444552", "pctChange": "6.468"},
        "ETHBRL": {"bid": "14224.7", "pctChange": "4.929"},
        "XAUBRL": {"bid": "22189.6", "pctChange": "-1.276882"},
    }
    monkeypatch.setattr(httpx, "get", lambda url, **kwargs: _RespostaFalsa(resposta_awesome))

    resultado = central_negocios_client._buscar_cambio()

    assert [item["codigo"] for item in resultado] == ["USD", "EUR", "GBP", "JPY", "BTC", "ETH", "XAU"]
    assert resultado[0]["valor"] == 5.1104
    assert resultado[0]["variacao_pct"] == -0.66
    bitcoin = next(item for item in resultado if item["codigo"] == "BTC")
    assert bitcoin["nome"] == "Bitcoin"
    assert bitcoin["valor"] == 444552.0


def test_buscar_cambio_moeda_faltando_na_resposta_e_ignorada(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "get", lambda url, **kwargs: _RespostaFalsa({"USDBRL": {"bid": "5.1", "pctChange": "0"}}))

    resultado = central_negocios_client._buscar_cambio()

    assert len(resultado) == 1
    assert resultado[0]["codigo"] == "USD"


def test_buscar_cambio_falha_de_rede_retorna_lista_vazia(monkeypatch: pytest.MonkeyPatch) -> None:
    def get_falso(url: str, **kwargs):
        raise httpx.ConnectError("sem rede")

    monkeypatch.setattr(httpx, "get", get_falso)

    assert central_negocios_client._buscar_cambio() == []


_RSS_EXEMPLO = """<rss><channel>
<item><title>Manchete 1</title><link>https://exemplo.com/1</link><pubDate>Mon, 21 Sep 2026 10:00:00 -0300</pubDate></item>
<item><title>Manchete 2</title><link>https://exemplo.com/2</link></item>
</channel></rss>"""


def test_parsear_rss_extrai_titulo_link_e_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "get", lambda url, **kwargs: _RespostaFalsa(text=_RSS_EXEMPLO))

    itens = central_negocios_client._parsear_rss("UOL Economia", "https://exemplo.com/feed")

    assert len(itens) == 2
    assert itens[0]["titulo"] == "Manchete 1"
    assert itens[0]["link"] == "https://exemplo.com/1"
    assert itens[0]["publicado_em"] is not None
    assert itens[1]["publicado_em"] is None


def test_parsear_rss_xml_invalido_retorna_lista_vazia(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(httpx, "get", lambda url, **kwargs: _RespostaFalsa(text="isto não é xml"))

    assert central_negocios_client._parsear_rss("UOL Economia", "https://exemplo.com/feed") == []


def test_buscar_noticias_falha_de_um_portal_nao_derruba_os_demais(monkeypatch: pytest.MonkeyPatch) -> None:
    def get_falso(url: str, **kwargs):
        if "uol" in url:
            raise httpx.ConnectError("uol fora do ar")
        return _RespostaFalsa(text=_RSS_EXEMPLO)

    monkeypatch.setattr(httpx, "get", get_falso)

    itens = central_negocios_client.buscar_noticias()

    portais = {item["portal"] for item in itens}
    assert "UOL Economia" not in portais
    assert "G1 Economia" in portais
    assert "InfoMoney" in portais
