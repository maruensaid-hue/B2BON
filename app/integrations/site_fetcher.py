from collections.abc import Callable

import httpx

SiteFetcher = Callable[[str], str]


def buscar_conteudo_site(dominio: str) -> str:
    """Fetch do site institucional — insumo para extração por IA (E2-H2)."""
    resposta = httpx.get(f"https://{dominio}", timeout=10.0, follow_redirects=True)
    resposta.raise_for_status()
    return resposta.text[:5000]
