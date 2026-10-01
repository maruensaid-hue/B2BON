from app.graph.client import Neo4jClient


class GrafoNulo(Neo4jClient):
    """Grafo que não grava nem lê nada — usado nas sessões de demonstração (D-083) para não espalhar dados fictícios
    no Neo4j compartilhado (que a limpeza do banco relacional não alcançaria)."""

    def __init__(self) -> None:  # sem driver: nenhuma conexão é aberta
        pass

    def close(self) -> None:
        pass

    def run_query(self, query: str, parameters: dict | None = None) -> list[dict]:
        return []
