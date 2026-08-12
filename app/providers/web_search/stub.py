import re

from app.providers.web_search.base import ResultadoBusca, WebSearchProvider


class StubWebSearchProvider(WebSearchProvider):
    """Devolve um resultado fixo e determinístico derivado da query —
    dev/teste, sem depender de fornecedor real nem gastar crédito de API."""

    def __init__(self) -> None:
        self.buscas: list[str] = []

    def buscar(self, query: str, limite: int = 5) -> list[ResultadoBusca]:
        self.buscas.append(query)
        nome = re.split(r"\s+site oficial\b", query, maxsplit=1)[0]
        slug = re.sub(r"[^a-z0-9]+", "", nome.lower())
        dominio = f"{slug or 'empresa'}.com.br"
        return [
            ResultadoBusca(
                titulo=f"{nome} - Site Oficial",
                url=f"https://www.{dominio}",
                descricao=f"Site institucional de {nome}.",
            )
        ]
