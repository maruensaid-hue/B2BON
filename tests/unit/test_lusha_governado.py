"""Adaptador Lusha no caminho governado: limite de revelação, e a separação entre falha certa (nada revelado) e desfecho ambíguo. Sem rede."""

import httpx
import pytest

from app.providers.contact_enrichment.base import ContactEnrichmentProvider, ContatoCandidato, FiltroContatos
from app.providers.contact_enrichment.lusha import LushaContactEnrichmentProvider


class _Resposta:
    def __init__(self, corpo=None, status_code=200, ilegivel=False):
        self._corpo, self.status_code, self._ilegivel = corpo or {}, status_code, ilegivel

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


BUSCA_3 = _Resposta({"results": [{"id": "c1"}, {"id": "c2"}, {"id": "c3"}]})
FILTRO = dict(nome_empresa="Empresa X", dominio="x.com.br")


def _lusha():
    return LushaContactEnrichmentProvider(api_key="chave-teste")


def test_sem_limite_nada_e_enviado(monkeypatch):
    enviados = _roteiro(monkeypatch, BUSCA_3, _Resposta({"results": []}))
    resultado = _lusha().buscar_contatos_governado(FiltroContatos(**FILTRO))
    assert resultado.estado == "erro_seguro" and resultado.detalhe == "limite_de_contatos_ausente"
    assert enviados == []


def test_revela_no_maximo_o_limite_e_cobra_so_o_que_veio(monkeypatch):
    enviados = _roteiro(monkeypatch, BUSCA_3, _Resposta({"results": [_contato(1), _contato(2)]}))
    resultado = _lusha().buscar_contatos_governado(FiltroContatos(**FILTRO, limite_contatos=2))
    assert resultado.estado == "ok" and len(resultado.contatos) == 2 and resultado.ids_provedor == ["c1", "c2"]
    assert enviados[0][1]["pagination"]["size"] == 2
    assert enviados[1] == ("enrich", {"ids": ["c1", "c2"], "reveal": ["emails", "phones"]})  # o terceiro id nunca é revelado


def test_provedor_que_devolve_acima_do_limite_e_truncado_no_adaptador(monkeypatch):
    _roteiro(monkeypatch, BUSCA_3, _Resposta({"results": [_contato(1), _contato(2), _contato(3)]}))
    resultado = _lusha().buscar_contatos_governado(FiltroContatos(**FILTRO, limite_contatos=1))
    assert len(resultado.contatos) == 1


def test_busca_sem_ids_e_sem_resultados_e_nao_chama_a_revelacao(monkeypatch):
    enviados = _roteiro(monkeypatch, _Resposta({"results": []}), _Resposta())
    resultado = _lusha().buscar_contatos_governado(FiltroContatos(**FILTRO, limite_contatos=2))
    assert resultado.estado == "sem_resultados" and [c for c, _ in enviados] == ["prospecting"]


@pytest.mark.parametrize("falha", [httpx.ReadTimeout("t"), httpx.ConnectError("c"), _Resposta(status_code=500), _Resposta(status_code=429)])
def test_falha_na_busca_e_sempre_segura_porque_nada_foi_revelado(monkeypatch, falha):
    _roteiro(monkeypatch, falha, _Resposta())
    assert _lusha().buscar_contatos_governado(FiltroContatos(**FILTRO, limite_contatos=2)).estado == "erro_seguro"


@pytest.mark.parametrize("falha,estado", [
    (httpx.ConnectError("c"), "erro_seguro"),            # nada saiu da máquina
    (httpx.ConnectTimeout("c"), "erro_seguro"),
    (_Resposta(status_code=429), "erro_seguro"),         # rejeitada pelo provedor
    (_Resposta(status_code=403), "erro_seguro"),
    (httpx.ReadTimeout("t"), "ambiguo"),                 # a revelação foi enviada e a resposta nunca chegou
    (httpx.WriteTimeout("t"), "ambiguo"),
    (httpx.RemoteProtocolError("queda"), "ambiguo"),
    (_Resposta(status_code=500), "ambiguo"),             # o servidor pode ter processado antes de falhar
    (_Resposta(status_code=503), "ambiguo"),
    (_Resposta(ilegivel=True), "ambiguo"),               # 200 com corpo ilegível: pode ter cobrado
])
def test_falha_na_revelacao_separa_certeza_de_ambiguidade(monkeypatch, falha, estado):
    _roteiro(monkeypatch, BUSCA_3, falha)
    resultado = _lusha().buscar_contatos_governado(FiltroContatos(**FILTRO, limite_contatos=2))
    assert resultado.estado == estado and resultado.ids_provedor == ["c1", "c2"]
    assert "chave-teste" not in (resultado.detalhe or "")


def test_revelacao_toda_com_erro_individual_vira_sem_resultados(monkeypatch):
    _roteiro(monkeypatch, BUSCA_3, _Resposta({"results": [{"id": "c1", "error": "not_found"}]}))
    assert _lusha().buscar_contatos_governado(FiltroContatos(**FILTRO, limite_contatos=1)).estado == "sem_resultados"


def test_caminho_legado_continua_igual_sem_limite(monkeypatch):
    enviados = _roteiro(monkeypatch, BUSCA_3, _Resposta({"results": [_contato(1)]}))
    assert len(_lusha().buscar_contatos(FiltroContatos(**FILTRO))) == 1
    assert enviados[0][1]["pagination"] == {"page": 0, "size": 20}


# --- padrão da porta (provedores sem custo) ---------------------------------------------------------------------------------------------------


class _Falho(ContactEnrichmentProvider):
    def buscar_contatos(self, filtro):
        raise RuntimeError("quebrou")


class _TresContatos(ContactEnrichmentProvider):
    def buscar_contatos(self, filtro):
        return [ContatoCandidato(nome=f"P{i}", cargo="CEO") for i in range(3)]


def test_porta_trata_excecao_desconhecida_como_ambigua():
    assert _Falho().buscar_contatos_governado(FiltroContatos(**FILTRO, limite_contatos=2)).estado == "ambiguo"


def test_porta_respeita_o_limite_e_distingue_vazio():
    assert len(_TresContatos().buscar_contatos_governado(FiltroContatos(**FILTRO, limite_contatos=2)).contatos) == 2
    assert _TresContatos().pago is False and _lusha().pago is True and _lusha().nome_provedor == "lusha"
