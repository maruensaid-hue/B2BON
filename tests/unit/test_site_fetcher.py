import socket
from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.integrations.site_fetcher import (
    _CAMINHOS_CANDIDATOS,
    HostNaoPublico,
    _validar_host_publico,
    buscar_conteudo_site,
)


def _addrinfo_para(ip: str):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 443))]


@pytest.mark.parametrize(
    "ip_privado",
    ["127.0.0.1", "169.254.169.254", "10.0.0.5", "192.168.1.1", "172.16.0.1", "0.0.0.0"],
)
def test_rejeita_ip_nao_publico(ip_privado):
    """SSRF real de produção: `Conta.dominio` é editável por qualquer
    usuário autenticado — sem esta trava, dava para apontar para a
    metadata de nuvem (169.254.169.254) ou pra rede interna do Render."""
    with patch("app.integrations.site_fetcher.socket.getaddrinfo", return_value=_addrinfo_para(ip_privado)):
        with pytest.raises(HostNaoPublico):
            _validar_host_publico("qualquer-dominio.com.br")


def test_aceita_ip_publico():
    with patch("app.integrations.site_fetcher.socket.getaddrinfo", return_value=_addrinfo_para("93.184.216.34")):
        _validar_host_publico("exemplo.com.br")  # não deve lançar


def test_dominio_que_nao_resolve_e_rejeitado():
    with patch("app.integrations.site_fetcher.socket.getaddrinfo", side_effect=socket.gaierror("no address")):
        with pytest.raises(HostNaoPublico):
            _validar_host_publico("dominio-inexistente.com.br")


def test_buscar_conteudo_site_bloqueia_dominio_apontando_para_ip_privado():
    with patch("app.integrations.site_fetcher.socket.getaddrinfo", return_value=_addrinfo_para("127.0.0.1")):
        with pytest.raises(HostNaoPublico):
            buscar_conteudo_site("empresa-maliciosa.com.br")


def test_caminhos_candidatos_incluem_vagas_abertas():
    """Pedido do usuário: enriquecimento de site também deve olhar vagas
    abertas (sinal de crescimento/contratação), não só sobre/investidores."""
    assert "/carreiras" in _CAMINHOS_CANDIDATOS
    assert "/vagas" in _CAMINHOS_CANDIDATOS


def test_buscar_conteudo_site_bloqueia_redirect_para_ip_privado():
    """Um domínio público que resolve OK, mas cujo servidor redireciona
    (302) para um IP interno — não basta validar só a primeira resolução
    de DNS, cada salto de redirect precisa ser revalidado."""

    def _getaddrinfo(host, *_args, **_kwargs):
        if host == "publico.com.br":
            return _addrinfo_para("93.184.216.34")
        return _addrinfo_para("169.254.169.254")

    resposta_redirect = MagicMock(spec=httpx.Response)
    resposta_redirect.is_redirect = True
    resposta_redirect.headers = {"location": "http://interno.local/roubado"}

    with (
        patch("app.integrations.site_fetcher.socket.getaddrinfo", side_effect=_getaddrinfo),
        patch("app.integrations.site_fetcher.httpx.get", return_value=resposta_redirect),
    ):
        with pytest.raises(HostNaoPublico):
            buscar_conteudo_site("publico.com.br")
