"""Base HTTP dos conectores externos (Fase 13).

Só leitura. Traduz o status HTTP para a semântica do framework de sync:
429/5xx → `ErroTransitorio` (o `com_retry` tenta de novo com backoff);
401/403 → `ErroCredencial` (não tenta de novo). A mensagem de erro nunca
carrega token nem corpo da resposta (pode ecoar credencial).

Hosts permitidos são fixos por conector (anti-SSRF): uma credencial
cadastrada pelo tenant não consegue apontar o servidor da B2B ON para
um endereço interno.
"""

from urllib.parse import urlsplit

import httpx

from app.contexts.integrations.contract import ErroCredencial, ErroTransitorio

# Testes injetam `httpx.MockTransport` aqui; em produção fica None (rede real).
TRANSPORTE_PADRAO: httpx.BaseTransport | None = None
TIMEOUT_SEGUNDOS = 30.0


class ErroConector(Exception):
    """Resposta inesperada do sistema externo (4xx que não é credencial)."""


def host_permitido(url: str, sufixos: tuple[str, ...]) -> bool:
    partes = urlsplit(url)
    host = (partes.hostname or "").lower()
    return (
        partes.scheme == "https"
        and partes.port in (None, 443)
        and not partes.username
        and any(host == s.lstrip(".") or host.endswith(s) for s in sufixos)
    )


class ClienteHttp:
    def __init__(self, sistema: str, base_url: str, headers: dict[str, str], transport: httpx.BaseTransport | None = None) -> None:
        self.sistema = sistema
        self._cliente = httpx.Client(
            base_url=base_url, headers=headers, timeout=TIMEOUT_SEGUNDOS,
            transport=transport or TRANSPORTE_PADRAO, follow_redirects=False,
        )

    def atualizar_header(self, nome: str, valor: str) -> None:
        self._cliente.headers[nome] = valor

    def _checar(self, resposta: httpx.Response) -> httpx.Response:
        codigo = resposta.status_code
        if codigo == 429 or codigo >= 500:
            raise ErroTransitorio(f"{self.sistema}: HTTP {codigo}")
        if codigo in (401, 403):
            raise ErroCredencial(f"{self.sistema}: credencial recusada (HTTP {codigo}). Reconecte a integração.")
        if codigo >= 300:
            raise ErroConector(f"{self.sistema}: HTTP {codigo}")
        return resposta

    def get(self, caminho: str, params: dict | None = None) -> dict:
        return self._checar(self._cliente.get(caminho, params=params)).json()

    def post(self, caminho: str, json: dict | None = None) -> dict:
        """POST de LEITURA (APIs de busca, ex.: HubSpot search)."""
        return self._checar(self._cliente.post(caminho, json=json)).json()

    def post_form(self, url: str, dados: dict) -> dict:
        return self._checar(self._cliente.post(url, data=dados)).json()
