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


def test_buscar_conteudo_site_respeita_orcamento_de_tempo_para_paginas_extras():
    """Raio-X de produção real: site institucional grande, com muitos
    links batendo nas palavras-chave, fazia a busca tentar página atrás
    de página até estourar o timeout do proxy do Render/Cloudflare — que
    devolve uma resposta sem os cabeçalhos de CORS da nossa API, e
    aparece pro usuário como "erro de CORS" (mascarando que o problema
    real era demora). Sem orçamento de tempo, nenhuma página além da
    home é tentada uma vez que o tempo já estourou."""
    home_resposta = MagicMock(spec=httpx.Response)
    home_resposta.is_redirect = False
    home_resposta.headers = {"content-type": "text/html; charset=utf-8"}
    home_resposta.text = '<html><a href="/sobre">Sobre</a></html>'
    home_resposta.raise_for_status = MagicMock()

    chamadas_get = MagicMock(return_value=home_resposta)
    valores_tempo = iter([0.0, 100.0])

    with (
        patch("app.integrations.site_fetcher.socket.getaddrinfo", return_value=_addrinfo_para("93.184.216.34")),
        patch("app.core.ssrf._requisicao_fixada", chamadas_get),
        patch("app.integrations.site_fetcher.time.monotonic", side_effect=lambda: next(valores_tempo)),
    ):
        resultado = buscar_conteudo_site("publico.com.br")

    assert chamadas_get.call_count == 1  # só a home — orçamento já estourado antes do primeiro candidato
    assert resultado.count("=== ") == 1


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
        patch("app.core.ssrf._requisicao_fixada", return_value=resposta_redirect),
    ):
        with pytest.raises(HostNaoPublico):
            buscar_conteudo_site("publico.com.br")


def _resposta(corpo: bytes, tipo: str | None, status: int = 200) -> httpx.Response:
    cabecalhos = {"content-type": tipo} if tipo else {}
    return httpx.Response(status, content=corpo, headers=cabecalhos, request=httpx.Request("GET", "https://publico.com.br/"))


def _com_resposta(resposta):
    return (
        patch("app.integrations.site_fetcher.socket.getaddrinfo", return_value=_addrinfo_para("93.184.216.34")),
        patch("app.core.ssrf._requisicao_fixada", return_value=resposta),
    )


@pytest.mark.parametrize("tipo", ["application/pdf", "image/png", "application/octet-stream", "application/zip", "application/json", "video/mp4"])
def test_home_com_tipo_de_conteudo_que_nao_e_pagina_e_recusada(tipo):
    from app.integrations.site_fetcher import ConteudoNaoSuportado

    p1, p2 = _com_resposta(_resposta(b"%PDF-1.7 binario", tipo))
    with p1, p2:
        with pytest.raises(ConteudoNaoSuportado, match="não suportado"):
            buscar_conteudo_site("publico.com.br")


@pytest.mark.parametrize("tipo", ["text/html", "text/html; charset=iso-8859-1", "TEXT/HTML", "application/xhtml+xml", "text/plain", None])
def test_tipos_de_pagina_e_resposta_sem_cabecalho_sao_aceitos(tipo):
    p1, p2 = _com_resposta(_resposta(b"<html><body>Ola mundo</body></html>", tipo))
    with p1, p2:
        assert "Ola mundo" in buscar_conteudo_site("publico.com.br")


def test_subpagina_com_tipo_inesperado_e_ignorada_sem_derrubar_a_coleta():
    respostas = iter([_resposta(b"<html>home</html>", "text/html"), _resposta(b"%PDF", "application/pdf")] + [_resposta(b"", "text/html", 404)] * 40)
    with patch("app.integrations.site_fetcher.socket.getaddrinfo", return_value=_addrinfo_para("93.184.216.34")),             patch("app.core.ssrf._requisicao_fixada", side_effect=lambda *a, **k: next(respostas)):
        resultado = buscar_conteudo_site("publico.com.br")
    assert resultado.count("=== ") == 1 and "home" in resultado


@pytest.mark.parametrize(
    "dominio",
    [
        "2130706433",              # 127.0.0.1 em decimal
        "0x7f.0.0.1",              # hexadecimal
        "0177.0.0.1",              # octal
        "127.1",                   # forma curta
        "[::1]",                   # IPv6 loopback
        "[::ffff:127.0.0.1]",      # IPv4 mapeado em IPv6
        "localhost",
        "LOCALHOST.",              # maiúsculas e ponto final
        "169.254.169.254",         # metadados de nuvem
        "user:senha@127.0.0.1",    # credenciais embutidas
        "127.0.0.1:6379",          # porta de serviço interno
    ],
)
def test_codificacoes_hostis_de_destino_interno_nao_chegam_a_rede(dominio):
    """Sem mockar o DNS: a resolução real de cada forma tem que cair em endereço não público (ou a URL ser recusada) antes de qualquer conexão."""
    with patch("app.core.ssrf._requisicao_fixada") as rede:
        with pytest.raises(httpx.HTTPError):
            buscar_conteudo_site(dominio)
    rede.assert_not_called()
