import re
from collections.abc import Callable

import httpx

SiteFetcher = Callable[[str], str]

_MAX_PAGINAS = 6
_MAX_CHARS_POR_PAGINA = 2500

# Caminhos comuns onde empresas brasileiras costumam publicar conteúdo
# relevante para pesquisa comercial — testados diretamente, sem depender de
# descobrir link nenhum (best-effort: falha de uma página nunca derruba as
# demais).
_CAMINHOS_CANDIDATOS = [
    "/sobre", "/sobre-nos", "/quem-somos", "/institucional",
    "/investidores", "/ri", "/relacao-com-investidores", "/resultados",
    "/blog", "/noticias", "/imprensa", "/novidades",
    "/privacidade", "/politica-de-privacidade", "/privacy-policy", "/privacy", "/lgpd",
]

# Palavras-chave usadas para reconhecer links internos relevantes na home,
# além dos caminhos fixos acima (cobre sites com URLs fora do padrão comum).
_PALAVRAS_CHAVE_LINK = (
    "sobre", "quem-somos", "institucional", "investidor", "\\bri\\b", "resultado",
    "blog", "noticia", "imprensa", "novidade", "historia", "timeline", "linha-do-tempo",
    "privacidade", "privacy", "lgpd",
)
_REGEX_LINKS_INTERNOS = re.compile(
    r'href="(/[^"#?]*(?:' + "|".join(_PALAVRAS_CHAVE_LINK) + r')[^"#?]*)"', re.IGNORECASE
)


def _buscar_pagina(base_url: str, caminho: str) -> str | None:
    try:
        resposta = httpx.get(f"{base_url}{caminho}", timeout=8.0, follow_redirects=True)
        resposta.raise_for_status()
        return resposta.text[:_MAX_CHARS_POR_PAGINA]
    except httpx.HTTPError:
        return None


def buscar_conteudo_site(dominio: str) -> str:
    """Pesquisa best-effort dentro do próprio site institucional — não só a
    home, mas também páginas de sobre/investidores/notícias/privacidade
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
    home = httpx.get(base_url, timeout=8.0, follow_redirects=True)
    home.raise_for_status()
    texto_home = home.text[:_MAX_CHARS_POR_PAGINA]

    paginas: dict[str, str] = {base_url: texto_home}

    caminhos_para_tentar = list(_CAMINHOS_CANDIDATOS)
    for link in _REGEX_LINKS_INTERNOS.findall(home.text):
        if link not in caminhos_para_tentar:
            caminhos_para_tentar.append(link)

    for caminho in caminhos_para_tentar:
        if len(paginas) >= _MAX_PAGINAS:
            break
        url = f"{base_url}{caminho}"
        if url in paginas:
            continue
        conteudo = _buscar_pagina(base_url, caminho)
        if conteudo:
            paginas[url] = conteudo

    return "\n\n".join(f"=== {url} ===\n{texto}" for url, texto in paginas.items())
