"""Sinais técnicos lidos no HTML bruto da home, sem IA: só regras reproduzíveis, cada achado com o trecho que o prova.

Adaptado ao mercado brasileiro: plataformas de vagas (Gupy, Solides, Kenoby...), plataformas de loja (VTEX, Nuvemshop, Tray...),
botão de WhatsApp e o crédito da agência no rodapé ("desenvolvido por"). Crédito sem rótulo não é registrado: atribuir a agência
errada numa mensagem é pior do que não citar nenhuma.
"""

import re
from dataclasses import dataclass
from html import unescape


@dataclass
class Achado:
    codigo: str
    num: float | None = None
    texto: str | None = None
    confianca: float = 0.9
    url: str | None = None
    trecho: str | None = None


_GOOGLE_ADS = re.compile(r"googleadservices\.com|google_conversion_id|gtag\(\s*['\"]config['\"]\s*,\s*['\"]AW-\d+", re.IGNORECASE)
_META_PIXEL = re.compile(r"connect\.facebook\.net/[^\"']*/fbevents\.js|fbq\(\s*['\"]init['\"]", re.IGNORECASE)
_WHATSAPP = re.compile(r"https?://(?:wa\.me|api\.whatsapp\.com/send|web\.whatsapp\.com/send)[^\"'\s<>]*", re.IGNORECASE)
_SCHEMA_ORG = re.compile(r"<script[^>]+application/ld\+json", re.IGNORECASE)

# Plataforma -> marcas inconfundíveis no HTML (caminhos de arquivo, domínios de CDN), nunca a palavra solta no texto.
_TECNOLOGIAS: dict[str, re.Pattern] = {
    "WordPress": re.compile(r"/wp-content/|/wp-includes/", re.IGNORECASE),
    "Wix": re.compile(r"static\.wixstatic\.com|static\.parastorage\.com", re.IGNORECASE),
    "VTEX": re.compile(r"vteximg\.com\.br|\.vtexassets\.com|vtex\.com\.br/", re.IGNORECASE),
    "Nuvemshop": re.compile(r"nuvemshop\.com\.br|tiendanube\.com|d26lpennugtm8s\.cloudfront\.net", re.IGNORECASE),
    "Shopify": re.compile(r"cdn\.shopify\.com", re.IGNORECASE),
    "Tray": re.compile(r"tcdn\.com\.br|tray\.com\.br", re.IGNORECASE),
    "Loja Integrada": re.compile(r"lojaintegrada\.com\.br", re.IGNORECASE),
    "RD Station": re.compile(r"d335luupugsy2\.cloudfront\.net|rdstation\.com\.br", re.IGNORECASE),
    "HubSpot": re.compile(r"js\.hs-scripts\.com|js\.hsforms\.net", re.IGNORECASE),
    "Google Tag Manager": re.compile(r"googletagmanager\.com/gtm\.js", re.IGNORECASE),
}

_VAGAS = re.compile(
    r"href=[\"'](https?://(?:[\w-]+\.)?(?:gupy\.io|vagas\.solides\.com\.br|jobs\.kenoby\.com|[\w-]+\.kenoby\.com|abler\.com\.br|"
    r"recrutei\.com\.br|vagas\.com\.br/vagas-de-|[\w-]+\.infojobs\.com\.br|jobs\.lever\.co|boards\.greenhouse\.io)[^\"']*)[\"']",
    re.IGNORECASE,
)
_PLATAFORMA_VAGAS = {"gupy.io": "Gupy", "solides": "Solides", "kenoby": "Kenoby", "abler": "Abler", "recrutei": "Recrutei",
                     "vagas.com.br": "Vagas.com", "infojobs": "InfoJobs", "lever.co": "Lever", "greenhouse.io": "Greenhouse"}

_AGENDAMENTO = re.compile(r"https?://(?:www\.)?(?:calendly\.com|doctoralia\.com\.br|cal\.com|agendor\.com\.br|simplesagenda\.com\.br)/[^\"'\s<>]*",
                          re.IGNORECASE)

# Crédito da agência: o rótulo é o que dá a confiança. "Desenvolvido por <a>Agência X</a>" = 0.9; texto sem link = 0.75.
_ROTULO_AGENCIA = r"(?:desenvolvido|criado|produzido|feito)\s+(?:com\s+.{1,20}?\s+)?por|site\s+por|powered\s+by|design\s+(?:by|por)"
_AGENCIA_COM_LINK = re.compile(rf"(?:{_ROTULO_AGENCIA})\s*:?\s*(?:<[^>]+>\s*)*<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
                               re.IGNORECASE | re.DOTALL)
_AGENCIA_TEXTO = re.compile(rf"(?:{_ROTULO_AGENCIA})\s*:?\s*([A-ZÀ-Ú][\w&.\- ]{{1,40}}?)(?=\s*(?:[<|©.]|$))", re.IGNORECASE)
# Plataforma de site não é agência ("Powered by WordPress").
_NAO_E_AGENCIA = re.compile(r"^(wordpress|wix|vtex|nuvemshop|shopify|tray|loja integrada|google|elementor|hostgator|locaweb|squarespace)\b",
                            re.IGNORECASE)

_TAG = re.compile(r"<[^>]+>")


def _limpar(texto: str) -> str:
    return re.sub(r"\s+", " ", unescape(_TAG.sub(" ", texto))).strip()


def _trecho(html: str, inicio: int, fim: int) -> str:
    return _limpar(html[max(0, inicio - 60): fim + 60])[:300]


def _dominio(url: str) -> str:
    return re.sub(r"^www\.", "", re.sub(r"^[a-z]+://", "", url.lower()).split("/")[0])


def _agencia(html: str, dominio_proprio: str) -> Achado | None:
    rodape = html[-60_000:]  # o crédito fica no fim da página; ler só o fim evita casar texto do conteúdo
    creditos_com_link = list(_AGENCIA_COM_LINK.finditer(rodape))
    for m in creditos_com_link:
        url, nome = m.group(1), _limpar(m.group(2))
        if not nome or _NAO_E_AGENCIA.match(nome) or (url.startswith("http") and _dominio(url) == _dominio(dominio_proprio)):
            continue
        return Achado("AGENCIA_NO_RODAPE", texto=nome[:80], confianca=0.9, url=url if url.startswith("http") else None,
                      trecho=_trecho(rodape, m.start(), m.end()))
    if creditos_com_link:  # o crédito existe e aponta para a própria empresa ou para uma plataforma: não há agência a registrar
        return None
    for m in _AGENCIA_TEXTO.finditer(_limpar(rodape)):
        nome = m.group(1).strip(" .-")
        if len(nome) >= 3 and not _NAO_E_AGENCIA.match(nome):
            return Achado("AGENCIA_NO_RODAPE", texto=nome[:80], confianca=0.75, trecho=m.group(0)[:200])
    return None


def extrair(html: str, dominio: str) -> list[Achado]:
    """Todos os sinais técnicos da home. Os booleanos são gravados também quando dão "não": a home foi lida, a ausência é observada."""
    achados: list[Achado] = []

    def booleano(codigo: str, padrao: re.Pattern) -> None:
        m = padrao.search(html)
        achados.append(Achado(codigo, num=1 if m else 0, confianca=0.9 if m else 0.7,
                              trecho=_trecho(html, m.start(), m.end()) if m else None))

    booleano("ANUNCIA_GOOGLE_ADS", _GOOGLE_ADS)
    booleano("ANUNCIA_META_ADS", _META_PIXEL)
    booleano("TEM_SCHEMA_ORG", _SCHEMA_ORG)

    whatsapp = _WHATSAPP.search(html)
    achados.append(Achado("WHATSAPP_NO_SITE", num=1 if whatsapp else 0, confianca=0.9 if whatsapp else 0.7,
                          url=whatsapp.group(0) if whatsapp else None))

    agendamento = _AGENDAMENTO.search(html)
    achados.append(Achado("AGENDAMENTO_ONLINE", num=1 if agendamento else 0, confianca=0.85 if agendamento else 0.6,
                          url=agendamento.group(0) if agendamento else None))

    tecnologias = [nome for nome, padrao in _TECNOLOGIAS.items() if padrao.search(html)]
    if tecnologias:
        achados.append(Achado("TECNOLOGIA_SITE", texto=", ".join(tecnologias), confianca=0.9))

    vagas = _VAGAS.search(html)
    if vagas:
        url = unescape(vagas.group(1))
        plataforma = next((nome for chave, nome in _PLATAFORMA_VAGAS.items() if chave in url.lower()), "outra")
        achados.append(Achado("VAGAS_EM_PLATAFORMA", num=1, texto=plataforma, confianca=0.9, url=url))

    agencia = _agencia(html, dominio)
    if agencia is not None:
        achados.append(agencia)
    return achados
