"""Adaptador do Hunter: leitura do formato DOCUMENTADO da API e tratamento de cada código de erro.

Estes testes usam respostas montadas a partir da documentação oficial; provam a leitura do formato, NÃO que a integração funciona contra a API real
(ainda não há chave para chamá-la)."""

import httpx
import pytest

from app.providers.contact_enrichment.base import FiltroContatos
from app.providers.contact_enrichment.hunter import ProvedorHunter


def _provedor(resposta: httpx.Response | Exception, capturadas: list[httpx.Request] | None = None) -> ProvedorHunter:
    def tratar(requisicao: httpx.Request) -> httpx.Response:
        if capturadas is not None:
            capturadas.append(requisicao)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta

    return ProvedorHunter("chave-de-teste", transport=httpx.MockTransport(tratar))


def _corpo(*itens: dict) -> dict:
    return {"data": {"domain": "empresa.com", "emails": list(itens)}, "meta": {"results": len(itens), "limit": 10, "offset": 0}}


def _item(**campos) -> dict:
    base = {"value": "ana.souza@empresa.com", "type": "personal", "provenance": "found", "confidence": 94, "first_name": "Ana", "last_name": "Souza",
            "position": "CEO", "seniority": "executive", "department": "executive", "linkedin": None, "phone_number": None,
            "verification": {"date": "2026-11-01", "status": "valid"}}
    return {**base, **campos}


def _filtro() -> FiltroContatos:
    return FiltroContatos(nome_empresa="Empresa", dominio="empresa.com", limite_contatos=3)


def test_le_o_formato_documentado_e_marca_o_e_mail_verificado():
    resposta = httpx.Response(200, json=_corpo(_item()), headers={"X-Credits-Used": "1"})

    resultado = _provedor(resposta).buscar_contatos_governado(_filtro())

    assert resultado.estado == "ok" and resultado.creditos_provedor == 1
    [contato] = resultado.contatos
    assert (contato.nome, contato.cargo, contato.email, contato.fonte) == ("Ana Souza", "CEO", "ana.souza@empresa.com", "hunter")
    assert contato.email_status == "verificado"


def test_envia_chave_no_cabecalho_e_filtros_de_pessoa_decisora_sem_expor_a_chave_na_url():
    capturadas: list[httpx.Request] = []

    _provedor(httpx.Response(200, json=_corpo()), capturadas).buscar_contatos_governado(_filtro())

    [requisicao] = capturadas
    assert requisicao.url.path == "/v2/domain-search" and requisicao.headers["X-API-KEY"] == "chave-de-teste"
    assert "chave-de-teste" not in str(requisicao.url)
    parametros = dict(requisicao.url.params)
    assert parametros["domain"] == "empresa.com" and parametros["type"] == "personal"
    assert parametros["seniority"] == "senior,executive" and parametros["required_field"] == "full_name,position" and parametros["limit"] == "3"


def test_limite_nunca_passa_de_10_no_plano_gratuito():
    capturadas: list[httpx.Request] = []

    _provedor(httpx.Response(200, json=_corpo()), capturadas).buscar_contatos_governado(FiltroContatos(nome_empresa="E", dominio="e.com", limite_contatos=50))

    assert dict(capturadas[0].url.params)["limit"] == "10"


def test_sem_dominio_pesquisa_pelo_nome_da_empresa():
    capturadas: list[httpx.Request] = []

    _provedor(httpx.Response(200, json=_corpo()), capturadas).buscar_contatos_governado(FiltroContatos(nome_empresa="Empresa X", limite_contatos=2))

    parametros = dict(capturadas[0].url.params)
    assert parametros["company"] == "Empresa X" and "domain" not in parametros


@pytest.mark.parametrize(
    ("item", "esperado"),
    [
        ({"verification": {"status": "valid"}, "provenance": "inferred"}, "verificado"),
        ({"verification": {"status": "accept_all"}, "provenance": "inferred"}, "inferido"),
        ({"verification": {"status": "unknown"}, "provenance": "found"}, "publicado"),
        ({"verification": None, "provenance": "found"}, "publicado"),
    ],
)
def test_status_do_e_mail_nunca_e_confirmado_e_o_deduzido_continua_retido(item, esperado):
    resultado = _provedor(httpx.Response(200, json=_corpo(_item(**item)))).buscar_contatos_governado(_filtro())

    assert resultado.contatos[0].email_status == esperado != "confirmado"


def test_ignora_item_sem_nome_ou_sem_e_mail_e_so_guarda_linkedin_que_e_endereco():
    corpo = _corpo(_item(first_name=None, last_name=None), _item(value=None), _item(linkedin="alexmacaw"),
                   _item(value="b@empresa.com", linkedin="https://www.linkedin.com/in/b"))

    resultado = _provedor(httpx.Response(200, json=corpo)).buscar_contatos_governado(
        FiltroContatos(nome_empresa="E", dominio="e.com", limite_contatos=5)
    )

    assert [c.linkedin_url for c in resultado.contatos] == [None, "https://www.linkedin.com/in/b"]


def test_sem_resultados_nao_e_erro():
    resultado = _provedor(httpx.Response(200, json=_corpo())).buscar_contatos_governado(_filtro())

    assert resultado.estado == "sem_resultados" and resultado.contatos == []


@pytest.mark.parametrize(
    ("status", "detalhe"),
    [(401, "hunter_chave_invalida"), (403, "hunter_limite_de_taxa"), (429, "hunter_sem_creditos"), (400, "hunter_requisicao_invalida")],
)
def test_codigos_de_erro_documentados(status, detalhe):
    resultado = _provedor(httpx.Response(status, json={"errors": [{"id": "x"}]})).buscar_contatos_governado(_filtro())

    assert resultado.estado == "erro_seguro" and resultado.detalhe == detalhe and resultado.contatos == []


def test_falha_de_rede_e_resposta_inesperada_sao_ambiguas_e_nunca_levantam():
    assert _provedor(httpx.ConnectTimeout("lento")).buscar_contatos_governado(_filtro()).estado == "ambiguo"
    assert _provedor(httpx.Response(502)).buscar_contatos_governado(_filtro()).estado == "ambiguo"
    assert _provedor(httpx.Response(200, content=b"nao e json")).buscar_contatos_governado(_filtro()).detalhe == "hunter_resposta_ilegivel"


def test_sem_chave_fica_indisponivel_e_nao_chama_a_rede():
    capturadas: list[httpx.Request] = []
    provedor = ProvedorHunter("", transport=httpx.MockTransport(lambda r: capturadas.append(r) or httpx.Response(200)))

    resultado = provedor.buscar_contatos_governado(_filtro())

    assert provedor.disponivel is False and resultado.detalhe == "hunter_sem_chave" and capturadas == []


def test_nao_e_provedor_pago_e_buscar_contatos_devolve_so_os_validos():
    provedor = _provedor(httpx.Response(200, json=_corpo(_item())))

    assert provedor.pago is False and len(provedor.buscar_contatos(_filtro())) == 1
