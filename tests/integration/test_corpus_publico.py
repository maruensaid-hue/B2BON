"""Corpus público de licitações entre tenants: um fato, várias cópias privadas; nada privado atravessa; coleta alimenta o corpus sem duplicar."""

from datetime import datetime

import pytest

from app.contexts.bids import coleta, licitacoes
from app.contexts.bids.fontes.base import LicitacaoExterna
from app.contexts.bids.fontes.pncp import PaginaPncp
from app.core.config import settings
from app.models.licitacao import Licitacao
from app.models.licitacao_publica import EventoLicitacaoPublica, LicitacaoPublica

A, B_, C = "tenant-teste", "tenant-outro", "tenant-terceiro"
URL = "/api/v1/bids"


def _ext(n=1, **kw) -> LicitacaoExterna:
    base = dict(fonte="PNCP", id_externo=f"CTRL-{n}", titulo=f"Aquisição de software {n}", objeto="Licenças de software", orgao_nome="Prefeitura X",
                orgao_cnpj="11222333000181", modalidade="PUBLIC_TENDER", data_publicacao=datetime(2026, 10, 1), prazo_proposta=datetime(2026, 11, 1),
                valor_estimado=1000.0, url=f"https://pncp.test/{n}", situacao_externa="Divulgada", atualizado_externo_em=datetime(2026, 10, 2),
                uf="SP", municipio="Campinas", modalidade_codigo=6)
    base.update(kw)
    return LicitacaoExterna(**base)


@pytest.fixture()
def headers(criar_usuario_autenticado, tenants_da_rede):
    return {B_: criar_usuario_autenticado(B_, "admin", "admin@b.com.br"), C: criar_usuario_autenticado(C, "admin", "admin@c.com.br")}


def test_dois_tenants_ingerindo_o_mesmo_edital_compartilham_um_unico_fato_publico(db_session, tenants_da_rede):
    licitacoes.ingerir_detalhado(db_session, A, None, [_ext()])
    licitacoes.ingerir_detalhado(db_session, B_, None, [_ext()])

    assert db_session.query(LicitacaoPublica).count() == 1
    copias = db_session.query(Licitacao).filter(Licitacao.fonte == "PNCP").all()
    assert {c.tenant_id for c in copias} == {A, B_}
    assert len({c.corpus_id for c in copias}) == 1 and copias[0].corpus_id is not None


def test_reingestao_nao_duplica_e_retificacao_chega_ao_fato_e_as_duas_copias(db_session, tenants_da_rede):
    for tenant in (A, B_):
        licitacoes.ingerir_detalhado(db_session, tenant, None, [_ext()])

    for tenant in (A, B_):
        licitacoes.ingerir_detalhado(db_session, tenant, None, [_ext(valor_estimado=9000.0, situacao_externa="Suspensa", atualizado_externo_em=datetime(2026, 10, 9))])

    publica = db_session.query(LicitacaoPublica).one()
    assert publica.valor_estimado == 9000.0 and publica.situacao_externa == "Suspensa" and publica.versao == 2
    assert db_session.query(Licitacao).filter_by(fonte="PNCP").count() == 2
    assert {c.valor_estimado for c in db_session.query(Licitacao).filter_by(fonte="PNCP")} == {9000.0}
    tipos = [e.tipo for e in db_session.query(EventoLicitacaoPublica).order_by(EventoLicitacaoPublica.id)]
    assert tipos.count("criada") == 1 and tipos.count("situacao_alterada") == 1  # o 2º tenant não repete o evento


def test_dado_privado_de_um_tenant_nunca_aparece_no_corpus_nem_para_o_outro(client, db_session, headers, tenants_da_rede):
    licitacoes.ingerir_detalhado(db_session, A, None, [_ext()])
    licitacoes.ingerir_detalhado(db_session, B_, None, [_ext()])
    minha = db_session.query(Licitacao).filter_by(tenant_id=A).one()
    segredo = "ESTRATEGIA-CONFIDENCIAL-DO-TENANT-A"
    editou = client.patch(f"{URL}/licitacoes/{minha.id}", json={"titulo": segredo, "vencedor": segredo, "motivo_resultado": segredo})
    assert editou.status_code == 200
    assert segredo in client.get(f"{URL}/licitacoes").text  # controle positivo: o dono enxerga o que gravou

    corpus_visto_por_b = client.get(f"{URL}/corpus", headers=headers[B_])
    detalhe_para_b = client.get(f"{URL}/corpus/{minha.corpus_id}", headers=headers[B_])
    licitacoes_de_b = client.get(f"{URL}/licitacoes", headers=headers[B_])

    for resposta in (corpus_visto_por_b, detalhe_para_b, licitacoes_de_b):
        assert resposta.status_code == 200 and segredo not in resposta.text
    assert detalhe_para_b.json()["titulo"] == "Aquisição de software 1"  # o fato público segue o da fonte
    assert not {"tenant_id", "vencedor", "valor_proposta", "conta_id", "oferta_id"} & set(detalhe_para_b.json())


def test_ja_acompanho_revela_so_o_proprio_vinculo_e_nao_quem_mais_acompanha(client, db_session, headers, tenants_da_rede):
    licitacoes.ingerir_detalhado(db_session, A, None, [_ext()])
    licitacoes.ingerir_detalhado(db_session, B_, None, [_ext()])

    de_a = client.get(f"{URL}/corpus").json()
    de_b = client.get(f"{URL}/corpus", headers=headers[B_]).json()
    de_c = client.get(f"{URL}/corpus", headers=headers[C]).json()

    assert [i["ja_acompanho"] for i in de_a] == [True] and [i["ja_acompanho"] for i in de_b] == [True]
    assert [i["ja_acompanho"] for i in de_c] == [False]  # C não vê que A e B acompanham; nenhum contador de seguidores


def test_acompanhar_e_idempotente_e_cria_copia_privada_ligada_ao_fato(client, db_session, headers, tenants_da_rede):
    licitacoes.ingerir_detalhado(db_session, A, None, [_ext()])
    corpus_id = db_session.query(LicitacaoPublica).one().id

    primeira = client.post(f"{URL}/corpus/{corpus_id}/acompanhar", headers=headers[C])
    segunda = client.post(f"{URL}/corpus/{corpus_id}/acompanhar", headers=headers[C])

    assert (primeira.status_code, segunda.status_code) == (201, 200) and primeira.json()["id"] == segunda.json()["id"]
    assert db_session.query(Licitacao).filter_by(tenant_id=C).count() == 1
    assert db_session.query(Licitacao).filter_by(tenant_id=C).one().corpus_id == corpus_id
    assert client.post(f"{URL}/corpus/999999/acompanhar", headers=headers[C]).status_code == 404


def test_excluir_a_copia_privada_de_um_tenant_nao_afeta_o_fato_nem_o_outro_tenant(db_session, tenants_da_rede):
    licitacoes.ingerir_detalhado(db_session, A, None, [_ext()])
    licitacoes.ingerir_detalhado(db_session, B_, None, [_ext()])

    db_session.query(Licitacao).filter_by(tenant_id=A).delete()
    db_session.commit()

    publica = db_session.query(LicitacaoPublica).one()
    copia_b = db_session.query(Licitacao).filter_by(tenant_id=B_).one()
    assert copia_b.corpus_id == publica.id and publica.titulo == "Aquisição de software 1"


def test_filtros_do_corpus_por_uf_texto_situacao_e_paginacao(client, db_session, tenants_da_rede):
    licitacoes.ingerir_detalhado(
        db_session, A, None, [_ext(1, uf="SP"), _ext(2, uf="RJ", objeto="Reforma de escola"), _ext(3, uf="SP", situacao_externa="Anulada")]
    )

    assert {i["fonte_id_externo"] for i in client.get(f"{URL}/corpus", params={"uf": "sp"}).json()} == {"CTRL-1", "CTRL-3"}
    assert [i["fonte_id_externo"] for i in client.get(f"{URL}/corpus", params={"q": "ESCOLA"}).json()] == ["CTRL-2"]
    assert [i["fonte_id_externo"] for i in client.get(f"{URL}/corpus", params={"situacao": "anulada"}).json()] == ["CTRL-3"]
    assert client.get(f"{URL}/corpus", params={"q": "%"}).json() == []  # coringas do LIKE são escapados, não viram "tudo"
    primeira = client.get(f"{URL}/corpus", params={"limite": 2})
    assert len(primeira.json()) == 2 and primeira.headers.get("X-Proximo-Cursor")
    segunda = client.get(f"{URL}/corpus", params={"limite": 2, "cursor": primeira.headers["X-Proximo-Cursor"]})
    assert len(segunda.json()) == 1


# --- Coleta agendada alimentando o corpus -------------------------------------------------------------------------------------------------


class _Fonte:
    def __init__(self, itens):
        self.itens = itens

    def buscar_pagina(self, *args):
        return PaginaPncp(self.itens, 1, 1, len(self.itens), 0, 1)


def test_coleta_de_dois_tenants_com_o_mesmo_filtro_grava_o_corpus_uma_vez(db_session, tenants_da_rede, monkeypatch):
    monkeypatch.setattr(settings, "pncp_habilitado", True)
    for tenant in (A, B_):
        coleta.salvar_configuracao(db_session, tenant, None, {"ativa": True, "modalidades": [6], "palavras_chave": ["software"]})
    fonte = _Fonte([_ext(1), _ext(2, titulo="Obra de ponte", objeto="Construção de ponte")])  # o 2º não casa com "software"
    agora = coleta._agora().replace(hour=12)

    for tenant in (A, B_):
        coleta.executar(db_session, tenant, fonte, "agendado", agora=agora, dormir=lambda s: None)
    coleta.executar(db_session, A, fonte, "manual", agora=agora, dormir=lambda s: None)  # recoleta: idempotente

    assert [p.fonte_id_externo for p in db_session.query(LicitacaoPublica)] == ["CTRL-1"]  # só o relevante entra; sem duplicar
    assert db_session.query(Licitacao).filter_by(fonte="PNCP").count() == 2
    assert db_session.query(EventoLicitacaoPublica).count() == 1
