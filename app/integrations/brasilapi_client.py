import re
from collections.abc import Callable

import httpx

BrasilApiClient = Callable[[str], dict]


def consultar_cnpj_brasilapi(cnpj: str) -> dict:
    """Consulta pontual de um CNPJ na BrasilAPI — API pública gratuita,
    sem chave, complementar ao snapshot em lote da Receita Federal
    (Onda E).

    Raio-X 2026-09-16: `Conta.cnpj` guarda hoje só dígitos em qualquer
    conta criada/editada a partir de agora (`conta_service._normalizar_cnpj`),
    mas contas já existentes podem ter ficado com o CNPJ formatado
    ("14.568.725/0001-95", digitado antes dessa correção) — a barra do
    formato humano quebrava a própria URL da BrasilAPI (interpretada como
    separador de caminho), devolvendo 404 mesmo pra um CNPJ válido.
    Normalizar aqui também cobre esses casos antigos, sem precisar de
    migração de dado nenhuma."""
    digitos = re.sub(r"\D", "", cnpj)
    resposta = httpx.get(f"https://brasilapi.com.br/api/cnpj/v1/{digitos}", timeout=10.0)
    resposta.raise_for_status()
    return resposta.json()
