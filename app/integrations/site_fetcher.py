import re
import socket  # noqa: F401 — os testes substituem `socket.getaddrinfo` por este módulo
import time
from collections.abc import Callable
from html.parser import HTMLParser

import httpx

from app.core.ssrf import DestinoNaoPublico, requisitar_publico, resolver_publico

SiteFetcher = Callable[[str], str]

_MAX_PAGINAS = 8
_MAX_CHARS_POR_PAGINA = 8000  # de TEXTO visível por página (a IA recebe só os primeiros 2.500 de cada; a extração determinística lê tudo)
_MAX_REDIRECTS = 3
_TIMEOUT_POR_REQUISICAO_SEGUNDOS = 5.0
# Teto de corpo por página (decodificado): só ~2.500 caracteres viram texto, o resto serve para achar links da home.
_MAX_BYTES_POR_PAGINA = 500_000
_PORTAS_PERMITIDAS = (80, 443)

# Orçamento de tempo pra tentar páginas além da home — sem isto, um site
# grande (muitos links batendo nas palavras-chave, ex.: raio-X real numa
# empresa com site institucional denso) podia empilhar dezenas de
# tentativas de ~20s cada (timeout x redirecionamentos) até estourar o
# timeout do proxy do Render/Cloudflare, que devolve uma resposta sem os
# cabeçalhos de CORS da nossa API — aparece pro usuário como erro de CORS,
# mascarando que o problema real era demora, não a origem da chamada.
_ORCAMENTO_PAGINAS_EXTRAS_SEGUNDOS = 15.0


# Domínio resolve para um IP privado/loopback/link-local/CGNAT/reservado — bloqueado para evitar SSRF (o domínio vem
# de `Conta.dominio`, campo editável por qualquer usuário autenticado do tenant). A regra mora em `app.core.ssrf`.
HostNaoPublico = DestinoNaoPublico


def _validar_host_publico(host: str) -> None:
    """Resolve o host e recusa qualquer IP fora do espaço público roteável (ver `app.core.ssrf.resolver_publico`)."""
    resolver_publico(host)

# Caminhos comuns onde empresas brasileiras costumam publicar conteúdo
# relevante para pesquisa comercial — testados diretamente, sem depender de
# descobrir link nenhum (best-effort: falha de uma página nunca derruba as
# demais).
_CAMINHOS_CANDIDATOS = [
    "/sobre", "/sobre-nos", "/quem-somos", "/institucional",
    "/investidores", "/ri", "/relacao-com-investidores", "/resultados",
    "/blog", "/noticias", "/imprensa", "/novidades",
    "/carreiras", "/vagas", "/trabalhe-conosco", "/jobs", "/careers",
    "/privacidade", "/politica-de-privacidade", "/privacy-policy", "/privacy", "/lgpd",
]

# Palavras-chave usadas para reconhecer links internos relevantes na home,
# além dos caminhos fixos acima (cobre sites com URLs fora do padrão comum).
_PALAVRAS_CHAVE_LINK = (
    "sobre", "quem-somos", "institucional", "investidor", "\\bri\\b", "resultado",
    "blog", "noticia", "imprensa", "novidade", "historia", "timeline", "linha-do-tempo",
    "vaga", "carreira", "emprego", "trabalhe-conosco", "\\bjob\\b", "career",
    "privacidade", "privacy", "lgpd",
)
_REGEX_LINKS_INTERNOS = re.compile(
    r'href="(/[^"#?]*(?:' + "|".join(_PALAVRAS_CHAVE_LINK) + r')[^"#?]*)"', re.IGNORECASE
)


QUEBRA = chr(10)


class _ExtratorDeTexto(HTMLParser):
    """HTML → texto visível: descarta script, estilo, cabeçalho técnico e SVG; quebra de linha nos blocos."""

    _IGNORAR = {"script", "style", "noscript", "head", "svg", "template", "iframe"}
    _BLOCOS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "footer", "header", "td", "address"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignorando = 0
        self.partes: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self._IGNORAR:
            self._ignorando += 1
        elif tag in self._BLOCOS:
            self.partes.append(QUEBRA)

    def handle_endtag(self, tag):
        if tag in self._IGNORAR and self._ignorando:
            self._ignorando -= 1
        elif tag in self._BLOCOS:
            self.partes.append(QUEBRA)

    def handle_data(self, data):
        if not self._ignorando:
            self.partes.append(data)


def html_para_texto(html: str) -> str:
    """Texto visível da página, com espaços colapsados. Conteúdo que não é HTML passa como está."""
    extrator = _ExtratorDeTexto()
    try:
        extrator.feed(html)
        extrator.close()
    except Exception:  # noqa: BLE001 — HTML quebrado nunca derruba a coleta; cai no texto bruto
        return re.sub(r"\s+", " ", html).strip()
    linhas = (re.sub(r"[^\S\n]+", " ", linha).strip() for linha in "".join(extrator.partes).split(QUEBRA))
    return QUEBRA.join(linha for linha in linhas if linha)


def _get_seguro(url: str) -> httpx.Response:
    """GET com as defesas de `app.core.ssrf` em cada salto: IP validado e usado na conexão (sem DNS rebinding),
    só portas 80/443, teto de bytes por página e redirecionamentos seguidos manualmente e revalidados."""
    return requisitar_publico(
        "GET", url, timeout=_TIMEOUT_POR_REQUISICAO_SEGUNDOS, max_bytes=_MAX_BYTES_POR_PAGINA,
        max_redirects=_MAX_REDIRECTS, portas=_PORTAS_PERMITIDAS,
    )


class ConteudoNaoSuportado(httpx.HTTPError):
    """O endereço respondeu, mas não com uma página de texto (PDF, imagem, arquivo binário, JSON...)."""


# Só estes tipos viram texto de página. Sem cabeçalho `Content-Type` a resposta é aceita (sites antigos); qualquer outro tipo é recusado em vez
# de decodificar bytes arbitrários como se fossem HTML.
_TIPOS_ACEITOS = {"text/html", "application/xhtml+xml", "text/plain"}


def _texto_da_pagina(resposta: httpx.Response) -> str:
    tipo = resposta.headers.get("content-type", "").split(";")[0].strip().lower()
    if tipo and tipo not in _TIPOS_ACEITOS:
        raise ConteudoNaoSuportado(f"Tipo de conteúdo não suportado: {tipo}")
    return html_para_texto(resposta.text)[:_MAX_CHARS_POR_PAGINA]


def _buscar_pagina(base_url: str, caminho: str) -> str | None:
    try:
        resposta = _get_seguro(f"{base_url}{caminho}")
        resposta.raise_for_status()
        return _texto_da_pagina(resposta)
    except httpx.HTTPError:
        return None


def buscar_conteudo_site(dominio: str) -> str:
    """Pesquisa best-effort dentro do próprio site institucional — não só a
    home, mas também páginas de sobre/investidores/notícias/vagas/privacidade
    quando existirem, para dar à IA sinais de crescimento, marcos e
    conformidade além do que a home sozinha mostra.

    Cada página encontrada entra no texto com um cabeçalho `=== url ===`,
    que também serve de registro de quais páginas foram de fato
    pesquisadas (usado por `conta_service.enriquecer` para montar o
    histórico da pesquisa). Nunca lança: páginas que falham são só
    ignoradas, e se nem a home responder, a exceção da home é propagada
    (sem home, não há o que pesquisar)."""
    # Defesa contra dominio ja vindo com protocolo (ex.: "https://empresa.com")
    # -- concatenar direto viraria "https://https://empresa.com" e quebrava
    # a resolucao de DNS (bug real de producao). O ponto de entrada
    # principal (conta_service) ja normaliza antes de salvar; isto aqui e
    # so uma segunda trava para dado que tenha chegado sem passar por la.
    dominio_limpo = re.sub(r"^[a-zA-Z]+://", "", dominio).strip("/")
    base_url = f"https://{dominio_limpo}"
    home = _get_seguro(base_url)
    home.raise_for_status()
    texto_home = _texto_da_pagina(home)

    paginas: dict[str, str] = {base_url: texto_home}

    caminhos_para_tentar = list(_CAMINHOS_CANDIDATOS)
    for link in _REGEX_LINKS_INTERNOS.findall(home.text):
        if link not in caminhos_para_tentar:
            caminhos_para_tentar.append(link)

    inicio_paginas_extras = time.monotonic()
    for caminho in caminhos_para_tentar:
        if len(paginas) >= _MAX_PAGINAS:
            break
        if time.monotonic() - inicio_paginas_extras >= _ORCAMENTO_PAGINAS_EXTRAS_SEGUNDOS:
            break
        url = f"{base_url}{caminho}"
        if url in paginas:
            continue
        conteudo = _buscar_pagina(base_url, caminho)
        if conteudo:
            paginas[url] = conteudo

    return "\n\n".join(f"=== {url} ===\n{texto}" for url, texto in paginas.items())
