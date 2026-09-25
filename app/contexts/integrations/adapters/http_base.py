"""Base HTTP dos conectores externos (Fase 13).

Só leitura. Traduz o status HTTP para a semântica do framework de sync:
429/5xx → `ErroTransitorio` (o `com_retry` tenta de novo com backoff);
401/403 → `ErroCredencial` (não tenta de novo). A mensagem de erro nunca
carrega token nem corpo da resposta (pode ecoar credencial).

Hosts permitidos são fixos por conector (anti-SSRF): uma credencial
cadastrada pelo tenant não consegue apontar o servidor da B2B ON para
um endereço interno.
"""

import json
import logging
import re
from collections.abc import Callable
from urllib.parse import urlsplit

import httpx

from app.contexts.integrations.contract import ErroCredencial, ErroTransitorio

_SEGREDO_NA_URL = re.compile(r"((?:api_)?token|access_token|refresh_token|client_secret)=[^&\s\"']+", re.IGNORECASE)


def ocultar_segredos(texto: str) -> str:
    return _SEGREDO_NA_URL.sub(r"\1=***", texto)


class _FiltroSegredos(logging.Filter):
    """O httpx loga a URL de cada requisição (INFO). APIs que só aceitam
    token na query (RD Station CRM v1) vazariam a credencial para o log."""

    def filter(self, record: logging.LogRecord) -> bool:
        mensagem = record.getMessage()
        limpa = ocultar_segredos(mensagem)
        if limpa != mensagem:
            record.msg, record.args = limpa, ()
        return True


logging.getLogger("httpx").addFilter(_FiltroSegredos())

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


class AcessoBearer:
    """Acesso por token Bearer com no máximo UMA renovação por instância
    (uma execução de sync). Subclasses dizem a URL base e como renovar
    (`_renovar_token` devolve o que muda nas credenciais); a renovação é
    entregue a `ao_renovar` para ser persistida criptografada."""

    SISTEMA = ""

    def _iniciar_acesso(self, credenciais: dict, transport: httpx.BaseTransport | None, ao_renovar: Callable[[dict], None] | None) -> None:
        self._credenciais = dict(credenciais)
        self._transport = transport
        self._ao_renovar = ao_renovar
        self._renovado = False
        self._http = self._novo_cliente()

    def _base_url(self) -> str:
        raise NotImplementedError

    def _renovar_token(self) -> dict:
        raise NotImplementedError

    def _pode_renovar(self) -> bool:
        return bool(self._credenciais.get("refresh_token"))

    def _novo_cliente(self) -> ClienteHttp:
        token = self._credenciais.get("access_token") or ""
        return ClienteHttp(self.SISTEMA, self._base_url(), {"Authorization": f"Bearer {token}", "Accept": "application/json"}, self._transport)

    def _cliente_auth(self, base_url: str) -> ClienteHttp:
        return ClienteHttp(self.SISTEMA, base_url, {"Accept": "application/json"}, self._transport)

    def _renovar(self) -> None:
        try:
            mudancas = self._renovar_token()
        except ErroConector as erro:  # 400 invalid_grant: refresh token revogado/expirado
            raise ErroCredencial(f"{self.SISTEMA}: não foi possível renovar o acesso. Reconecte a integração.") from erro
        if not mudancas.get("access_token"):
            raise ErroCredencial(f"{self.SISTEMA}: renovação de token devolveu resposta inválida.")
        self._credenciais.update(mudancas)
        self._http = self._novo_cliente()
        self._renovado = True
        if self._ao_renovar:
            self._ao_renovar(dict(self._credenciais))

    def _com_renovacao(self, chamada: Callable[[], dict]) -> dict:
        try:
            return chamada()
        except ErroCredencial:
            if self._renovado or not self._pode_renovar():
                raise
            self._renovar()
            return chamada()

    def _get(self, caminho: str, params: dict | None = None) -> dict:
        return self._com_renovacao(lambda: self._http.get(caminho, params))

    def _post(self, caminho: str, corpo: dict) -> dict:
        return self._com_renovacao(lambda: self._http.post(caminho, corpo))


def persistidor(db, conexao) -> Callable[[dict], None]:
    """Grava credenciais renovadas na conexão (coluna criptografada)."""

    def persistir(novas: dict) -> None:
        conexao.credenciais = json.dumps(novas)
        db.commit()

    return persistir
