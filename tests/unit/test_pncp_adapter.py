"""Adapter PNCP: contrato do serviço real (modalidade obrigatória, paginação), retentativa com espera e respostas inválidas."""

import httpx
import pytest

from app.contexts.bids.fontes.pncp import TAMANHO_PAGINA, ErroFonte, FontePncp
from app.services.errors import ValidacaoFalhou

REGISTRO = {
    "numeroControlePNCP": "11222333000181-1-000045/2026", "objetoCompra": "Aquisição de licenças de software",
    "valorTotalEstimado": 1500.0, "dataPublicacaoPncp": "2026-10-19T10:00:00", "modalidadeId": 6, "srp": False,
    "anoCompra": 2026, "sequencialCompra": 45, "orgaoEntidade": {"cnpj": "11222333000181", "razaoSocial": "MUNICIPIO X"},
}


def _fonte(respostas, esperas=None):
    """Devolve (fonte, requisicoes). `respostas`: lista de httpx.Response ou exceções, consumidas em ordem."""
    fila, requisicoes = list(respostas), []

    def responder(request):
        requisicoes.append(request)
        item = fila.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    cliente = httpx.Client(base_url="https://pncp.test/api/consulta/v1", transport=httpx.MockTransport(responder))
    esperas = [] if esperas is None else esperas
    return FontePncp(cliente, dormir=esperas.append), requisicoes


def _ok(registros=None, **meta):
    corpo = {"data": registros if registros is not None else [REGISTRO], "totalRegistros": 1, "totalPaginas": 1, "numeroPagina": 1,
             "paginasRestantes": 0, "empty": False, **meta}
    return httpx.Response(200, json=corpo)


def test_pedido_leva_a_modalidade_obrigatoria_o_tamanho_maximo_e_a_uf():
    fonte, requisicoes = _fonte([_ok()])

    pagina = fonte.buscar_pagina("20261019", "20261020", 6, pagina=2, uf="sp")

    params = dict(requisicoes[0].url.params)
    assert params == {"dataInicial": "20261019", "dataFinal": "20261020", "pagina": "2", "tamanhoPagina": str(TAMANHO_PAGINA),
                      "codigoModalidadeContratacao": "6", "uf": "SP"}
    assert TAMANHO_PAGINA == 50  # 100 é recusado pelo serviço real
    assert (len(pagina.itens), pagina.total_paginas, pagina.total_registros, pagina.tentativas) == (1, 1, 1, 1)


@pytest.mark.parametrize("modalidade", [None, 0, 20])
def test_sem_modalidade_valida_nao_chega_a_rede(modalidade):
    fonte, requisicoes = _fonte([])
    with pytest.raises(ValidacaoFalhou):
        fonte.buscar_pagina("20261019", "20261020", modalidade)
    assert requisicoes == []


def test_registro_sem_numero_de_controle_e_contado_como_ignorado():
    fonte, _ = _fonte([_ok([REGISTRO, {"objetoCompra": "sem identificador"}])])
    pagina = fonte.buscar_pagina("20261019", "20261020", 6)
    assert (len(pagina.itens), pagina.ignorados) == (1, 1)


def test_204_e_pagina_vazia():
    fonte, _ = _fonte([httpx.Response(204)])
    assert fonte.buscar_pagina("20261019", "20261020", 6).itens == []


def test_falha_transitoria_repete_com_espera_progressiva_e_conta_as_tentativas():
    esperas = []
    fonte, requisicoes = _fonte([httpx.Response(503), httpx.ConnectTimeout("lento"), _ok()], esperas)

    pagina = fonte.buscar_pagina("20261019", "20261020", 6)

    assert len(requisicoes) == 3 and pagina.tentativas == 3
    assert esperas == [1.0, 2.0]


def test_429_respeita_retry_after_com_teto():
    esperas = []
    fonte, _ = _fonte([httpx.Response(429, headers={"retry-after": "7"}), httpx.Response(429, headers={"retry-after": "999"}), _ok()], esperas)
    fonte.buscar_pagina("20261019", "20261020", 6)
    assert esperas == [7.0, 30.0]


def test_desiste_apos_o_limite_de_tentativas_sem_loop_infinito():
    esperas = []
    fonte, requisicoes = _fonte([httpx.Response(500)] * 5, esperas)

    with pytest.raises(ErroFonte) as erro:
        fonte.buscar_pagina("20261019", "20261020", 6)

    assert len(requisicoes) == 3 and erro.value.tentativas == 3 and erro.value.transitorio is True
    assert "500" in str(erro.value)


def test_requisicao_invalida_400_nao_repete():
    fonte, requisicoes = _fonte([httpx.Response(400, json={"message": "Tamanho de página inválido"})])
    with pytest.raises(ErroFonte) as erro:
        fonte.buscar_pagina("20261019", "20261020", 6)
    assert len(requisicoes) == 1 and erro.value.transitorio is False


@pytest.mark.parametrize("resposta", [httpx.Response(200, content=b"<html>manutencao</html>"), httpx.Response(200, json=[1, 2]),
                                       httpx.Response(200, json={"data": "nao-e-lista"})])
def test_resposta_invalida_e_erro_claro(resposta):
    fonte, _ = _fonte([resposta])
    with pytest.raises(ErroFonte, match="PNCP devolveu"):
        fonte.buscar_pagina("20261019", "20261020", 6)


def test_buscar_mantem_a_assinatura_antiga_devolvendo_so_os_itens():
    fonte, _ = _fonte([_ok()])
    itens = fonte.buscar("20261019", "20261020", 6)
    assert [i.id_externo for i in itens] == ["11222333000181-1-000045/2026"]
