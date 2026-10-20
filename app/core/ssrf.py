"""Saída HTTP segura para destinos informados por usuário (crawler de site, webhooks de saída).

Defesas, todas aplicadas a CADA salto (inclusive redirecionamentos):

* só `http`/`https`, sem credenciais embutidas na URL e (opcional) só as portas permitidas;
* o host é resolvido UMA vez, todo IP resultante precisa ser público (`is_global`; cobre loopback, redes privadas,
  link-local/metadata de nuvem, CGNAT 100.64/10, IPv6 local e IPv4 embutido em IPv6);
* a conexão é feita no IP JÁ VALIDADO (o `Host` e o SNI seguem o nome original). Validar o nome e deixar o cliente
  resolver de novo permitiria DNS rebinding (o DNS responde público na checagem e interno na conexão);
* corpo lido em streaming com teto de bytes decodificados (resposta gigante e compressão abusiva são cortadas);
* sem `trust_env` (proxy de ambiente) e sem seguir redirecionamento automático.
"""

import ipaddress
import socket
from urllib.parse import urlsplit

import httpx

_ESQUEMAS = ("http", "https")
_SUFIXOS_INTERNOS = (".localhost", ".local", ".internal", ".localdomain", ".lan", ".home.arpa")
_CABECALHOS_DE_TRANSPORTE = {"content-encoding", "content-length", "transfer-encoding"}


class DestinoNaoPublico(httpx.HTTPError):
    """O destino é inválido ou resolve para um endereço que não é da internet pública."""

    def __init__(self, mensagem: str) -> None:
        super().__init__(mensagem)


def ip_publico(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def resolver_publico(host: str, porta: int = 443) -> list[str]:
    """Resolve `host` e devolve os IPs, recusando se qualquer um não for público."""
    try:
        enderecos = socket.getaddrinfo(host, porta)
    except socket.gaierror as erro:
        raise DestinoNaoPublico(f"Não foi possível resolver o domínio: {host}") from erro
    ips: list[str] = []
    for *_, sockaddr in enderecos:
        ip = ipaddress.ip_address(sockaddr[0])
        if not ip_publico(ip):
            raise DestinoNaoPublico(f"Domínio resolve para um IP não público ({ip}): {host}")
        if sockaddr[0] not in ips:
            ips.append(sockaddr[0])
    if not ips:
        raise DestinoNaoPublico(f"Não foi possível resolver o domínio: {host}")
    return ips


def validar_url_sem_dns(url: str) -> str:
    """Validação estática (sem rede) para cadastrar uma URL: esquema, host presente, sem credenciais, e sem IP
    literal ou nome claramente interno. A resolução de DNS acontece no envio (`requisitar_publico`)."""
    partes = urlsplit(url)
    if partes.scheme not in _ESQUEMAS or not partes.hostname:
        raise DestinoNaoPublico("URL inválida: use http ou https com um endereço completo.")
    if partes.username or partes.password:
        raise DestinoNaoPublico("URL inválida: não use usuário ou senha no endereço.")
    host = partes.hostname.lower().rstrip(".")
    sem_ponto = "." not in host and ":" not in host
    if host == "localhost" or host.endswith(_SUFIXOS_INTERNOS) or sem_ponto:
        raise DestinoNaoPublico("O endereço informado é interno e não pode ser usado.")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return url
    if not ip_publico(ip):
        raise DestinoNaoPublico("O endereço informado é interno e não pode ser usado.")
    return url


def _porta(partes) -> int:
    return partes.port or (443 if partes.scheme == "https" else 80)


def _requisicao_fixada(metodo: str, url: str, ips: list[str], *, timeout: float, max_bytes: int,
                       headers: dict[str, str] | None, content: bytes | None,
                       transport: httpx.BaseTransport | None = None) -> httpx.Response:
    """Uma requisição conectando no IP validado. Devolve a resposta com o corpo decodificado e cortado em `max_bytes`."""
    partes = urlsplit(url)
    host = partes.hostname or ""
    ultimo_erro: Exception | None = None
    for ip in ips:
        alvo = httpx.URL(url).copy_with(host=ip)
        cabecalhos = {"Host": partes.netloc.rsplit("@", 1)[-1], **(headers or {})}
        extensoes = {"sni_hostname": host} if partes.scheme == "https" else {}
        try:
            with httpx.Client(timeout=timeout, follow_redirects=False, trust_env=False, transport=transport) as cliente:
                with cliente.stream(metodo, alvo, headers=cabecalhos, content=content, extensions=extensoes) as resposta:
                    corpo = bytearray()
                    for pedaco in resposta.iter_bytes():
                        corpo.extend(pedaco)
                        if len(corpo) >= max_bytes:
                            del corpo[max_bytes:]
                            break
                    cabecalhos_resposta = [(k, v) for k, v in resposta.headers.multi_items() if k.lower() not in _CABECALHOS_DE_TRANSPORTE]
                    return httpx.Response(
                        resposta.status_code, headers=cabecalhos_resposta, content=bytes(corpo),
                        request=httpx.Request(metodo, url),
                    )
        except (httpx.ConnectError, httpx.ConnectTimeout) as erro:
            ultimo_erro = erro
            continue
    raise ultimo_erro or DestinoNaoPublico(f"Não foi possível conectar: {host}")


def requisitar_publico(metodo: str, url: str, *, timeout: float = 5.0, max_bytes: int = 1_000_000, max_redirects: int = 0,
                       headers: dict[str, str] | None = None, content: bytes | None = None,
                       portas: tuple[int, ...] | None = None) -> httpx.Response:
    """Requisição a um destino público. `max_redirects > 0` segue redirecionamentos (só GET), revalidando cada salto."""
    for _ in range(max_redirects + 1):
        partes = urlsplit(url)
        if partes.scheme not in _ESQUEMAS or not partes.hostname:
            raise DestinoNaoPublico(f"URL não permitida: {url}")
        if partes.username or partes.password:
            raise DestinoNaoPublico("URL com credenciais embutidas não é permitida.")
        porta = _porta(partes)
        if portas is not None and porta not in portas:
            raise DestinoNaoPublico(f"Porta não permitida: {porta}")
        ips = resolver_publico(partes.hostname, porta)
        resposta = _requisicao_fixada(metodo, url, ips, timeout=timeout, max_bytes=max_bytes, headers=headers, content=content)
        if max_redirects and metodo == "GET" and resposta.is_redirect:
            proxima = resposta.headers.get("location")
            if not proxima:
                return resposta
            url = str(httpx.URL(url).join(proxima))
            continue
        return resposta
    raise DestinoNaoPublico(f"Excedeu o limite de {max_redirects} redirecionamentos: {url}")
