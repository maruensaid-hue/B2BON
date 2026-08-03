from collections.abc import Callable

import httpx

BrasilApiClient = Callable[[str], dict]


def consultar_cnpj_brasilapi(cnpj: str) -> dict:
    """Consulta pontual de um CNPJ na BrasilAPI — API pública gratuita,
    sem chave, complementar ao snapshot em lote da Receita Federal
    (Onda E)."""
    resposta = httpx.get(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj}", timeout=10.0)
    resposta.raise_for_status()
    return resposta.json()
