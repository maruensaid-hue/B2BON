"""Adaptador Lusha no caminho governado: limite de revelação, tamanho de página, dados a revelar, `waterfallEnabled` desligado, consumo MEDIDO pela
resposta (`billing.creditsCharged`) e a separação entre falha certa (nada cobrado na etapa) e desfecho ambíguo. Sem rede."""

import httpx
import pytest

from app.providers.contact_enrichment.base import ContactEnrichmentProvider, ContatoCandidato, FiltroContatos
from app.providers.contact_enrichment.lusha import LushaContactEnrichmentProvider


class _Resposta:
    def __init__(self, corpo=None, status_code=200, ilegivel=False):
        self._corpo, self.status_code, self._ilegivel = corpo if corpo is not None else {}, status_code, ilegivel

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("erro", request=None, response=self)

    def json(self):
        if self._ilegivel:
            raise ValueError("corpo ilegível")
        return self._corpo


def _roteiro(monkeypatch, busca, revelacao):
    """`busca`/`revelacao`: _Resposta ou exceção a levantar. Devolve a lista de (caminho, corpo) enviados."""
    enviados = []

    def _post(url, json, headers, timeout):
        enviados.append((url.rsplit("/", 1)[-1], json))
        alvo = busca if url.endswith("/prospecting") else revelacao
        if isinstance(alvo, Exception):
            raise alvo
        return alvo

    monkeypatch.setattr(httpx, "post", _post)
    return enviados


def _contato(n):
    return {"id": f"c{n}", "firstName": f"Pessoa{n}", "lastName": "Teste", "jobTitle": {"title": "CEO"}, "emails": [{"email": f"p{n}@x.com"}], "phones": []}


def _busca(cobrado=3, ids=("c1", "c2", "c3")):
    return _Resposta({"results": [{"id": i} for i in ids], "billing": {"creditsCharged": cobrado, "resultsReturned": len(ids)}})


def _enrich(cobrado, *contatos):
    return _Resposta({"results": list(contatos), "billing": {"creditsCharged": cobrado, "resultsReturned": len(contatos)}})


FILTRO = dict(nome_empresa="Empresa X", dominio="x.com.br", limite_contatos=2, tamanho_pagina=10, revelar=["emails", "phones"])


def _lusha():
    return LushaContactEnrichmentProvider(api_key="chave-teste")


def test_documentacao_oficial_vira_atributos_do_adaptador():
    lusha = _lusha()
    assert (lusha.nome_provedor, lusha.pago, lusha.tamanho_pagina_minimo, lusha.max_contatos_por_consulta) == ("lusha", True, 10, 100)


@pytest.mark.parametrize("ajuste,detalhe", [
    (dict(limite_contatos=None), "limite_de_contatos_ausente"),
    (dict(limite_contatos=0), "limite_de_contatos_ausente"),
    (dict(tamanho_pagina=None), "tamanho_de_pagina_invalido"),
    (dict(tamanho_pagina=9), "tamanho_de_pagina_invalido"),       # a Lusha aceita de 10 a 100
    (dict(tamanho_pagina=101), "tamanho_de_pagina_invalido"),
    (dict(limite_contatos=11, tamanho_pagina=10), "tamanho_de_pagina_invalido"),
    (dict(revelar=None), "dados_a_revelar_invalidos"),
    (dict(revelar=[]), "dados_a_revelar_invalidos"),
    (dict(revelar=["emails", "tudo"]), "dados_a_revelar_invalidos"),
])
def test_parametros_ausentes_ou_invalidos_nada_e_enviado(monkeypatch, ajuste, detalhe):
    enviados = _roteiro(monkeypatch, _busca(), _enrich(0))
    resultado = _lusha().buscar_contatos_governado(FiltroContatos(**{**FILTRO, **ajuste}))
    assert resultado.estado == "erro_seguro" and resultado.detalhe == detalhe and enviados == []


def test_pagina_dados_a_revelar_e_waterfall_vem_da_politica_e_o_consumo_e_o_medido(monkeypatch):
    enviados = _roteiro(monkeypatch, _busca(cobrado=3), _enrich(7, _contato(1), _contato(2)))
    resultado = _lusha().buscar_contatos_governado(FiltroContatos(**FILTRO))
    assert resultado.estado == "ok" and len(resultado.contatos) == 2 and resultado.ids_provedor == ["c1", "c2"]
    assert (resultado.creditos_busca, resultado.creditos_revelacao, resultado.creditos_provedor) == (3, 7, 10)  # medido, não 1 por contato
    assert enviados[0][1]["pagination"] == {"page": 0, "size": 10}
    assert enviados[1] == ("enrich", {"ids": ["c1", "c2"], "reveal": ["emails", "phones"], "waterfallEnabled": False})  # o 3º id nunca é revelado


def test_so_revela_o_que_a_politica_pede(monkeypatch):
    enviados = _roteiro(monkeypatch, _busca(), _enrich(2, _contato(1), _contato(2)))
    _lusha().buscar_contatos_governado(FiltroContatos(**{**FILTRO, "revelar": ["emails"]}))
    assert enviados[1][1]["reveal"] == ["emails"]


def test_provedor_que_devolve_acima_do_limite_e_truncado_no_adaptador(monkeypatch):
    _roteiro(monkeypatch, _busca(), _enrich(3, _contato(1), _contato(2), _contato(3)))
    assert len(_lusha().buscar_contatos_governado(FiltroContatos(**{**FILTRO, "limite_contatos": 1})).contatos) == 1


def test_busca_sem_ids_e_sem_resultados_mas_a_busca_cobrada_e_medida(monkeypatch):
    enviados = _roteiro(monkeypatch, _busca(cobrado=1, ids=()), _Resposta())
    resultado = _lusha().buscar_contatos_governado(FiltroContatos(**FILTRO))
    assert resultado.estado == "sem_resultados" and resultado.creditos_provedor == 1 and [c for c, _ in enviados] == ["prospecting"]


@pytest.mark.parametrize("falha,estado", [
    (httpx.ConnectError("c"), "erro_seguro"),            # nada saiu da máquina
    (httpx.ConnectTimeout("c"), "erro_seguro"),
    (_Resposta(status_code=402), "erro_seguro"),         # sem créditos na conta do provedor: nada processado
    (_Resposta(status_code=429), "erro_seguro"),         # limite de taxa
    (_Resposta(status_code=403), "erro_seguro"),
    (httpx.ReadTimeout("t"), "ambiguo"),                 # a busca foi enviada e a resposta nunca chegou: pode ter cobrado
    (_Resposta(status_code=500), "ambiguo"),
    (_Resposta(ilegivel=True), "ambiguo"),
])
def test_falha_na_busca_tambem_separa_certeza_de_ambiguidade_porque_a_busca_cobra(monkeypatch, falha, estado):
    _roteiro(monkeypatch, falha, _enrich(0))
    resultado = _lusha().buscar_contatos_governado(FiltroContatos(**FILTRO))
    assert resultado.estado == estado and resultado.creditos_provedor is None


def test_busca_sem_medicao_e_ambigua(monkeypatch):
    _roteiro(monkeypatch, _Resposta({"results": [{"id": "c1"}]}), _enrich(1, _contato(1)))
    resultado = _lusha().buscar_contatos_governado(FiltroContatos(**FILTRO))
    assert resultado.estado == "ambiguo" and resultado.detalhe == "medicao_ausente_na_busca"


@pytest.mark.parametrize("falha,estado,detalhe", [
    (httpx.ConnectError("c"), "erro_seguro", "revelacao_conexao"),
    (_Resposta(status_code=402), "erro_seguro", "revelacao_sem_creditos"),
    (_Resposta(status_code=429), "erro_seguro", "revelacao_limite_de_taxa"),
    (_Resposta(status_code=403), "erro_seguro", "revelacao_rejeitada"),
    (httpx.ReadTimeout("t"), "ambiguo", "revelacao_timeout"),
    (httpx.WriteTimeout("t"), "ambiguo", "revelacao_timeout"),
    (httpx.RemoteProtocolError("queda"), "ambiguo", "revelacao_transporte"),
    (_Resposta(status_code=500), "ambiguo", "revelacao_servidor"),
    (_Resposta(ilegivel=True), "ambiguo", "revelacao_resposta_ilegivel"),
])
def test_falha_na_revelacao_mantem_o_consumo_da_busca_ja_medido(monkeypatch, falha, estado, detalhe):
    _roteiro(monkeypatch, _busca(cobrado=3), falha)
    resultado = _lusha().buscar_contatos_governado(FiltroContatos(**FILTRO))
    assert (resultado.estado, resultado.detalhe) == (estado, detalhe)
    assert resultado.creditos_busca == 3 and resultado.ids_provedor == ["c1", "c2"]  # só os ids dentro do limite chegam à revelação
    assert resultado.creditos_provedor == 3  # a busca já foi cobrada e medida; só a execução decide o que liquidar (seguro) ou reter (ambíguo)
    assert "chave-teste" not in (resultado.detalhe or "")


def test_revelacao_sem_medicao_e_ambigua(monkeypatch):
    _roteiro(monkeypatch, _busca(), _Resposta({"results": [_contato(1)]}))
    resultado = _lusha().buscar_contatos_governado(FiltroContatos(**FILTRO))
    assert resultado.estado == "ambiguo" and resultado.detalhe == "medicao_ausente_na_revelacao" and resultado.creditos_busca == 3


def test_medicao_invalida_nao_conta_como_medicao(monkeypatch):
    for invalido in (-1, True, "3", 2.5, None):
        _roteiro(monkeypatch, _Resposta({"results": [{"id": "c1"}], "billing": {"creditsCharged": invalido}}), _enrich(1, _contato(1)))
        assert _lusha().buscar_contatos_governado(FiltroContatos(**FILTRO)).estado == "ambiguo", invalido


def test_waterfall_sem_creditos_na_revelacao_e_ambiguo(monkeypatch):
    resposta = _Resposta({"results": [], "status": "OUT_OF_CREDITS", "billing": {"creditsCharged": 0, "resultsReturned": 0}})
    _roteiro(monkeypatch, _busca(), resposta)
    assert _lusha().buscar_contatos_governado(FiltroContatos(**FILTRO)).detalhe == "revelacao_sem_creditos"


def test_revelacao_toda_com_erro_individual_vira_sem_resultados_com_o_consumo_medido(monkeypatch):
    _roteiro(monkeypatch, _busca(cobrado=3), _enrich(0, {"id": "c1", "error": {"code": "NOT_FOUND", "message": "x"}}))
    resultado = _lusha().buscar_contatos_governado(FiltroContatos(**FILTRO))
    assert resultado.estado == "sem_resultados" and resultado.creditos_provedor == 3


def test_uso_e_tarifas_do_provedor(monkeypatch):
    corpo = {"credits": {"total": 5000, "used": 200, "remaining": 4800}, "pricing": {"revealEmail": {"credits": 1, "perQuantity": 1},
                                                                                       "revealPhone": {"credits": 5, "perQuantity": 1}}}
    monkeypatch.setattr(httpx, "get", lambda url, headers, timeout: _Resposta(corpo))
    uso = _lusha().consultar_uso()
    assert (uso.creditos_total, uso.creditos_usados, uso.creditos_restantes) == (5000, 200, 4800)
    assert uso.tarifas["revealPhone"] == {"credits": 5, "perQuantity": 1}


def test_caminho_legado_continua_igual_sem_limite(monkeypatch):
    enviados = _roteiro(monkeypatch, _busca(), _enrich(1, _contato(1)))
    assert len(_lusha().buscar_contatos(FiltroContatos(nome_empresa="Empresa X", dominio="x.com.br"))) == 1
    assert enviados[0][1]["pagination"] == {"page": 0, "size": 20}


# --- padrão da porta (provedores sem custo) ---------------------------------------------------------------------------------------------------


class _Falho(ContactEnrichmentProvider):
    def buscar_contatos(self, filtro):
        raise RuntimeError("quebrou")


class _TresContatos(ContactEnrichmentProvider):
    def buscar_contatos(self, filtro):
        return [ContatoCandidato(nome=f"P{i}", cargo="CEO") for i in range(3)]


def test_porta_trata_excecao_desconhecida_como_ambigua():
    assert _Falho().buscar_contatos_governado(FiltroContatos(**FILTRO)).estado == "ambiguo"


def test_porta_respeita_o_limite_e_nao_mede_consumo():
    resultado = _TresContatos().buscar_contatos_governado(FiltroContatos(**FILTRO))
    assert len(resultado.contatos) == 2 and resultado.creditos_provedor is None
    assert _TresContatos().pago is False


def test_provedor_sem_consulta_de_uso_levanta_not_implemented():
    with pytest.raises(NotImplementedError):
        _TresContatos().consultar_uso()
