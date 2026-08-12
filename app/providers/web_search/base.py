from abc import ABC, abstractmethod

from pydantic import BaseModel


class ResultadoBusca(BaseModel):
    titulo: str
    url: str
    descricao: str


class WebSearchProvider(ABC):
    """Porta para busca na web — hoje usada só para descobrir o site
    oficial de uma conta sem domínio cadastrado (`conta_service.enriquecer`).
    Nunca usada para automatizar login/scraping de redes sociais."""

    @abstractmethod
    def buscar(self, query: str, limite: int = 5) -> list[ResultadoBusca]:
        raise NotImplementedError
