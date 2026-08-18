from app.providers.web_search.base import ResultadoBusca, WebSearchProvider


class WebSearchDesativadoProvider(WebSearchProvider):
    """No-op para produção sem `BRAVE_SEARCH_API_KEY` configurada —
    diferente de outros stubs, `StubWebSearchProvider` **fabrica** um
    domínio plausível (`nomedaempresa.com.br`) a partir da própria
    query, então usá-lo em produção não falha silenciosamente: ele
    inventa um site que não existe, `conta_service.enriquecer` salva
    esse domínio fantasma na conta e a busca seguinte quebra com "não
    foi possível resolver o domínio". Sem fornecedor contratado, a
    descoberta de domínio simplesmente não encontra nada — cai no erro
    já existente pedindo pra cadastrar o domínio manualmente."""

    def buscar(self, query: str, limite: int = 5) -> list[ResultadoBusca]:
        return []
