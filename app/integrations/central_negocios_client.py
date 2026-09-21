import xml.etree.ElementTree as ET
from collections.abc import Callable
from email.utils import parsedate_to_datetime
from typing import TypedDict

import httpx

_TIMEOUT_SEGUNDOS = 6.0
_USER_AGENT = "Mozilla/5.0 (compatible; B2BON-CentralNegocios/1.0)"

# Ticker do Yahoo Finance pro Ibovespa — API pública não-documentada, sem
# chave, mas amplamente usada por ferramentas financeiras livres (ex.: a
# biblioteca `yfinance`); é a única fonte encontrada com o índice B3 real
# sem exigir cadastro/token pago (AwesomeAPI só cobre câmbio, brapi.dev
# exige token pra índices).
_URL_IBOVESPA = "https://query1.finance.yahoo.com/v8/finance/chart/%5EBVSP"

# AwesomeAPI (economia.awesomeapi.com.br) — API brasileira pública de
# câmbio, sem chave, mesma fonte já usada informalmente por diversas
# ferramentas financeiras nacionais.
_URL_CAMBIO = "https://economia.awesomeapi.com.br/last/{pares}"
_MOEDAS = (("USD", "Dólar americano"), ("EUR", "Euro"), ("GBP", "Libra esterlina"), ("JPY", "Iene japonês"))

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


class Ibovespa(TypedDict):
    pontos: float
    variacao_pct: float


class Mercado(TypedDict):
    ibovespa: Ibovespa | None
    cambio: list[CotacaoMoeda]


class Noticia(TypedDict):
    portal: str
    titulo: str
    link: str
    publicado_em: str | None


MercadoClient = Callable[[], Mercado]
NoticiasClient = Callable[[], list[Noticia]]


def _buscar_ibovespa() -> Ibovespa | None:
    try:
        resposta = httpx.get(
            _URL_IBOVESPA,
            params={"interval": "1d", "range": "5d"},
            headers={"User-Agent": _USER_AGENT},
            timeout=_TIMEOUT_SEGUNDOS,
        )
        resposta.raise_for_status()
        meta = resposta.json()["chart"]["result"][0]["meta"]
        return {
            "pontos": round(float(meta["regularMarketPrice"]), 2),
            "variacao_pct": round(float(meta["regularMarketChangePercent"]), 2),
        }
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
        return None


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
    """Cotações reais de mercado (B3 + câmbio) — nunca inventa um número:
    fonte indisponível vira `None`/lista vazia, tratado pelo frontend como
    "indisponível no momento", nunca um valor fabricado."""
    return {"ibovespa": _buscar_ibovespa(), "cambio": _buscar_cambio()}


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
