import httpx

from app.core.config import settings
from app.providers.web_search.base import ResultadoBusca, WebSearchProvider

_URL_BUSCA = "https://api.search.brave.com/res/v1/web/search"


class BraveSearchProvider(WebSearchProvider):
    """Brave Search API — índice próprio, não depende do Google.
    https://api.search.brave.com/res/v1/web/search"""

    def buscar(self, query: str, limite: int = 5) -> list[ResultadoBusca]:
        resposta = httpx.get(
            _URL_BUSCA,
            params={"q": query, "count": limite},
            headers={
                "Accept": "application/json",
                "X-Subscription-Token": settings.brave_search_api_key,
            },
            timeout=8.0,
        )
        resposta.raise_for_status()
        resultados = resposta.json().get("web", {}).get("results", [])
        return [
            ResultadoBusca(
                titulo=item.get("title", ""),
                url=item.get("url", ""),
                descricao=item.get("description", ""),
            )
            for item in resultados[:limite]
        ]
