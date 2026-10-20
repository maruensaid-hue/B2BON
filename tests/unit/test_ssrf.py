"""Saída HTTP segura (app.core.ssrf): destinos internos, DNS rebinding, redirecionamento, tamanho e esquema."""

import gzip
import ipaddress
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch

import httpx
import pytest

from app.core import ssrf
from app.core.ssrf import DestinoNaoPublico, ip_publico, requisitar_publico, validar_url_sem_dns


def _addrinfo(ip: str, porta: int = 443):
    familia = socket.AF_INET6 if ":" in ip else socket.AF_INET
    return [(familia, socket.SOCK_STREAM, 6, "", (ip, porta))]


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1", "10.1.2.3", "172.16.0.9", "192.168.0.1", "169.254.169.254", "0.0.0.0",
        "100.64.0.1",  # CGNAT: não é "private" para o módulo ipaddress, mas não é internet pública
        "::1", "fc00::1", "fe80::1", "::ffff:127.0.0.1", "::ffff:169.254.169.254", "224.0.0.1",
    ],
)
def test_ip_nao_publico_e_recusado(ip):
    assert ip_publico(ipaddress.ip_address(ip)) is False


@pytest.mark.parametrize("ip", ["8.8.8.8", "93.184.216.34", "2606:4700:4700::1111"])
def test_ip_publico_e_aceito(ip):
    assert ip_publico(ipaddress.ip_address(ip)) is True


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd", "ftp://exemplo.com/x", "gopher://exemplo.com", "javascript:alert(1)",
        "http://localhost/admin", "http://servidor.local/", "http://metadata.internal/", "http://intranet/",
        "http://127.0.0.1:8000/", "http://169.254.169.254/latest/meta-data/", "http://[::1]/",
        "https://usuario:senha@exemplo.com/", "https:///sem-host",
    ],
)
def test_url_estatica_invalida_ou_interna_e_recusada(url):
    with pytest.raises(DestinoNaoPublico):
        validar_url_sem_dns(url)


def test_url_estatica_publica_passa_sem_consultar_dns():
    with patch("app.core.ssrf.socket.getaddrinfo", side_effect=AssertionError("não deve resolver DNS")):
        assert validar_url_sem_dns("https://hooks.exemplo.com.br/b2bon") == "https://hooks.exemplo.com.br/b2bon"


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://exemplo.com", "gopher://exemplo.com/_x"])
def test_esquema_nao_http_nao_chega_a_rede(url):
    with patch("app.core.ssrf._requisicao_fixada") as rede:
        with pytest.raises(DestinoNaoPublico):
            requisitar_publico("GET", url)
    rede.assert_not_called()


def test_porta_fora_da_lista_e_recusada():
    with patch("app.core.ssrf.socket.getaddrinfo", return_value=_addrinfo("93.184.216.34", 6379)):
        with patch("app.core.ssrf._requisicao_fixada") as rede:
            with pytest.raises(DestinoNaoPublico, match="Porta"):
                requisitar_publico("GET", "http://exemplo.com:6379/", portas=(80, 443))
    rede.assert_not_called()


def test_dns_rebinding_a_conexao_usa_o_ip_validado_e_o_dns_e_consultado_uma_vez_por_salto():
    """O DNS responde público na validação e interno depois. A conexão precisa usar o IP validado, nunca resolver de novo."""
    respostas = iter([_addrinfo("93.184.216.34"), _addrinfo("127.0.0.1")])
    resolucoes = []

    def _getaddrinfo(host, porta, *a, **k):
        resolucoes.append(host)
        return next(respostas)

    ok = httpx.Response(200, content=b"ok", request=httpx.Request("GET", "https://exemplo.com/"))
    with patch("app.core.ssrf.socket.getaddrinfo", side_effect=_getaddrinfo), \
            patch("app.core.ssrf._requisicao_fixada", return_value=ok) as rede:
        requisitar_publico("GET", "https://exemplo.com/")

    assert resolucoes == ["exemplo.com"]
    assert rede.call_args.args[2] == ["93.184.216.34"]


def test_redirecionamento_para_ip_interno_e_bloqueado_no_salto():
    redirect = httpx.Response(302, headers={"location": "http://interno.exemplo.com/x"},
                              request=httpx.Request("GET", "https://exemplo.com/"))

    def _getaddrinfo(host, porta, *a, **k):
        return _addrinfo("93.184.216.34" if host == "exemplo.com" else "169.254.169.254", porta)

    with patch("app.core.ssrf.socket.getaddrinfo", side_effect=_getaddrinfo), \
            patch("app.core.ssrf._requisicao_fixada", return_value=redirect):
        with pytest.raises(DestinoNaoPublico, match="não público"):
            requisitar_publico("GET", "https://exemplo.com/", max_redirects=3)


def test_laco_de_redirecionamento_para_no_limite():
    redirect = httpx.Response(302, headers={"location": "https://exemplo.com/"}, request=httpx.Request("GET", "https://exemplo.com/"))
    with patch("app.core.ssrf.socket.getaddrinfo", return_value=_addrinfo("93.184.216.34")), \
            patch("app.core.ssrf._requisicao_fixada", return_value=redirect) as rede:
        with pytest.raises(DestinoNaoPublico, match="limite"):
            requisitar_publico("GET", "https://exemplo.com/", max_redirects=2)
    assert rede.call_count == 3


def test_post_nao_segue_redirecionamento():
    redirect = httpx.Response(302, headers={"location": "http://127.0.0.1/"}, request=httpx.Request("POST", "https://exemplo.com/"))
    with patch("app.core.ssrf.socket.getaddrinfo", return_value=_addrinfo("93.184.216.34")), \
            patch("app.core.ssrf._requisicao_fixada", return_value=redirect) as rede:
        resposta = requisitar_publico("POST", "https://exemplo.com/", content=b"{}", max_redirects=3)
    assert resposta.status_code == 302
    assert rede.call_count == 1


class _Servidor(BaseHTTPRequestHandler):
    def log_message(self, *a):  # silencioso
        pass

    def do_GET(self):
        if self.path == "/gzip":
            corpo = gzip.compress(b"A" * 5_000_000)  # ~5 KB comprimido, 5 MB descomprimido
            self.send_response(200)
            self.send_header("Content-Encoding", "gzip")
        else:
            corpo = b"B" * 3_000_000
            self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_POST(self):
        tamanho = int(self.headers.get("Content-Length", 0))
        recebido = self.rfile.read(tamanho)
        resposta = f"{self.headers.get('Host')}|{recebido.decode()}".encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(resposta)))
        self.end_headers()
        self.wfile.write(resposta)


@pytest.fixture()
def servidor_local():
    servidor = HTTPServer(("127.0.0.1", 0), _Servidor)
    thread = threading.Thread(target=servidor.serve_forever, daemon=True)
    thread.start()
    yield servidor.server_address[1]
    servidor.shutdown()


def test_corpo_gigante_e_cortado_no_teto(servidor_local):
    """Conexão real (loopback, sem passar pela checagem de IP): o corpo de 3 MB vira no máximo `max_bytes`."""
    resposta = ssrf._requisicao_fixada("GET", f"http://alvo.exemplo.com:{servidor_local}/grande", ["127.0.0.1"],
                                       timeout=5, max_bytes=10_000, headers=None, content=None)
    assert resposta.status_code == 200
    assert len(resposta.content) == 10_000


def test_compressao_abusiva_e_cortada_apos_descompactar(servidor_local):
    resposta = ssrf._requisicao_fixada("GET", f"http://alvo.exemplo.com:{servidor_local}/gzip", ["127.0.0.1"],
                                       timeout=5, max_bytes=20_000, headers=None, content=None)
    assert resposta.status_code == 200
    assert len(resposta.content) == 20_000
    assert resposta.content == b"A" * 20_000


def test_conecta_no_ip_validado_mantendo_o_host_original(servidor_local):
    resposta = ssrf._requisicao_fixada("POST", f"http://alvo.exemplo.com:{servidor_local}/hook", ["127.0.0.1"],
                                       timeout=5, max_bytes=10_000, headers={"Content-Type": "application/json"}, content=b'{"a":1}')
    assert resposta.text == f'alvo.exemplo.com:{servidor_local}|{{"a":1}}'
