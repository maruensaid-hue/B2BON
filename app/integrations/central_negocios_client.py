import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import TypedDict
from urllib.parse import quote

import httpx

_TIMEOUT_SEGUNDOS = 6.0
_USER_AGENT = "Mozilla/5.0 (compatible; B2BON-CentralNegocios/1.0)"

# Yahoo Finance chart API — pública, não-documentada, sem chave, mas
# amplamente usada por ferramentas financeiras livres (ex.: a biblioteca
# `yfinance`); é a única fonte encontrada com os índices reais sem exigir
# cadastro/token pago (AwesomeAPI só cobre câmbio/cripto, brapi.dev exige
# token pra índices). Mesmo endpoint devolve a série histórica usada pro
# gráfico de linha, não só a cotação do momento.
_URL_CHART_YAHOO = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
_INDICES = (
    ("^BVSP", "Ibovespa"),
    ("^DJI", "Dow Jones (Nova Iorque)"),
    ("^IXIC", "Nasdaq"),
    ("000001.SS", "Xangai"),
    ("^N225", "Tóquio (Nikkei)"),
)

# AwesomeAPI (economia.awesomeapi.com.br) — API brasileira pública de
# câmbio/cripto/metais, sem chave, mesma fonte já usada informalmente por
# diversas ferramentas financeiras nacionais. `nome` aqui é o rótulo curto
# mostrado na janela de cotações (raio-X 2026-09-21: usuário pediu o
# formato "USD = R$ 5,00 | Bitcoin = R$ 134.000,00").
_URL_CAMBIO = "https://economia.awesomeapi.com.br/last/{pares}"
_MOEDAS = (
    ("USD", "USD"),
    ("EUR", "EUR"),
    ("GBP", "GBP"),
    ("JPY", "JPY"),
    ("BTC", "Bitcoin"),
    ("ETH", "Ethereum"),
    ("XAU", "Ouro"),
)

# RSS reais dos próprios portais — nunca manchete/link inventado (mesma
# cautela de "IA não pode inventar fato" aplicada aqui a dado editorial).
_LIMITE_POR_PORTAL = 6
_PORTAIS_RSS = (
    ("UOL Economia", "https://rss.uol.com.br/feed/economia.xml"),
    ("G1 Economia", "https://g1.globo.com/rss/g1/economia/"),
    ("InfoMoney", "https://www.infomoney.com.br/feed/"),
)


class CotacaoMoeda(TypedDict):
    codigo: str
    nome: str
    valor: float
    variacao_pct: float


class PontoSerie(TypedDict):
    data: str
    valor: float


class Indice(TypedDict):
    nome: str
    pontos: float
    variacao_pct: float
    serie: list[PontoSerie]


class Mercado(TypedDict):
    indices: list[Indice]
    cambio: list[CotacaoMoeda]


class Noticia(TypedDict):
    portal: str
    titulo: str
    link: str
    publicado_em: str | None


MercadoClient = Callable[[], Mercado]
NoticiasClient = Callable[[], list[Noticia]]


def _buscar_indice(ticker: str, nome: str) -> Indice | None:
    try:
        resposta = httpx.get(
            _URL_CHART_YAHOO.format(ticker=quote(ticker, safe="")),
            params={"interval": "1d", "range": "1mo"},
            headers={"User-Agent": _USER_AGENT},
            timeout=_TIMEOUT_SEGUNDOS,
        )
        resposta.raise_for_status()
        resultado = resposta.json()["chart"]["result"][0]
        meta = resultado["meta"]
        timestamps = resultado.get("timestamp") or []
        fechamentos = resultado["indicators"]["quote"][0].get("close") or []
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
        return None

    serie: list[PontoSerie] = []
    for instante, fechamento in zip(timestamps, fechamentos, strict=False):
        if fechamento is None:
            continue
        try:
            data_formatada = datetime.fromtimestamp(instante, tz=UTC).strftime("%d/%m")
            serie.append({"data": data_formatada, "valor": round(float(fechamento), 2)})
        except (TypeError, ValueError, OSError):
            continue

    try:
        return {
            "nome": nome,
            "pontos": round(float(meta["regularMarketPrice"]), 2),
            "variacao_pct": round(float(meta["regularMarketChangePercent"]), 2),
            "serie": serie,
        }
    except (KeyError, TypeError, ValueError):
        return None


def buscar_indices() -> list[Indice]:
    """Índices das 3 bolsas pedidas (B3, NY, Nasdaq) com série do último
    mês pro gráfico de linha do carrossel — falha de um índice nunca
    derruba os demais."""
    indices: list[Indice] = []
    for ticker, nome in _INDICES:
        indice = _buscar_indice(ticker, nome)
        if indice:
            indices.append(indice)
    return indices


def _buscar_cambio() -> list[CotacaoMoeda]:
    try:
        pares = ",".join(f"{codigo}-BRL" for codigo, _ in _MOEDAS)
        resposta = httpx.get(_URL_CAMBIO.format(pares=pares), timeout=_TIMEOUT_SEGUNDOS)
        resposta.raise_for_status()
        dados = resposta.json()
    except (httpx.HTTPError, ValueError):
        return []

    resultado: list[CotacaoMoeda] = []
    for codigo, nome in _MOEDAS:
        item = dados.get(f"{codigo}BRL")
        if not item:
            continue
        try:
            resultado.append({
                "codigo": codigo,
                "nome": nome,
                "valor": round(float(item["bid"]), 4),
                "variacao_pct": round(float(item["pctChange"]), 2),
            })
        except (KeyError, TypeError, ValueError):
            continue
    return resultado


def buscar_mercado() -> Mercado:
    """Cotações reais de mercado (índices de bolsa + câmbio/cripto/ouro) —
    nunca inventa um número: fonte indisponível vira lista vazia, tratado
    pelo frontend como "indisponível no momento", nunca um valor fabricado."""
    return {"indices": buscar_indices(), "cambio": _buscar_cambio()}


def _parsear_rss(portal: str, url: str) -> list[Noticia]:
    try:
        resposta = httpx.get(url, headers={"User-Agent": _USER_AGENT}, timeout=_TIMEOUT_SEGUNDOS, follow_redirects=True)
        resposta.raise_for_status()
        raiz = ET.fromstring(resposta.text)
    except (httpx.HTTPError, ET.ParseError):
        return []

    itens: list[Noticia] = []
    for item in raiz.findall(".//item")[:_LIMITE_POR_PORTAL]:
        titulo = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        if not titulo or not link:
            continue
        publicado_em = None
        pub_date_bruto = item.findtext("pubDate")
        if pub_date_bruto:
            try:
                publicado_em = parsedate_to_datetime(pub_date_bruto).isoformat()
            except (TypeError, ValueError):
                publicado_em = None
        itens.append({"portal": portal, "titulo": titulo, "link": link, "publicado_em": publicado_em})
    return itens


def buscar_noticias() -> list[Noticia]:
    """Últimas matérias reais dos RSS de negócios de cada portal — link e
    título vêm direto da fonte, nunca gerados/resumidos por IA. Falha de um
    portal nunca derruba os demais (mesmo espírito best-effort de
    `site_fetcher.buscar_conteudo_site`)."""
    noticias: list[Noticia] = []
    for portal, url in _PORTAIS_RSS:
        noticias.extend(_parsear_rss(portal, url))
    return noticias
