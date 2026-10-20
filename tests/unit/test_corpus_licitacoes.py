"""Corpus público comum de licitações: idempotência, retificação, situação, ordem, corrida, recuperação e separação público/privado."""

from datetime import datetime, timedelta

import pytest

from app.contexts.bids import corpus
from app.contexts.bids.fontes.base import LicitacaoExterna
from app.models.licitacao_publica import EventoLicitacaoPublica, LicitacaoPublica

AGORA = datetime(2026, 10, 20, 12, 0)


def _ext(n=1, **sobrescrever) -> LicitacaoExterna:
    base = dict(
        fonte="PNCP", id_externo=f"CTRL-{n}", titulo=f"Aquisição de software {n}", objeto="Licenças de software de gestão", orgao_nome="Prefeitura X",
        orgao_cnpj="11222333000181", modalidade="PUBLIC_TENDER", data_publicacao=datetime(2026, 10, 1), prazo_proposta=datetime(2026, 11, 1),
        valor_estimado=1000.0, url=f"https://pncp.test/{n}", situacao_externa="Divulgada", atualizado_externo_em=datetime(2026, 10, 2),
        uf="SP", municipio="Campinas", modalidade_codigo=6,
    )
    base.update(sobrescrever)
    return LicitacaoExterna(**base)


def _eventos(db, publica_id):
    return [(e.tipo, e.versao) for e in db.query(EventoLicitacaoPublica).filter_by(licitacao_publica_id=publica_id).order_by(EventoLicitacaoPublica.id)]


def test_registrar_o_mesmo_edital_duas_vezes_nao_duplica_nem_gera_evento(db_session):
    primeira = corpus.registrar(db_session, [_ext()], AGORA)
    segunda = corpus.registrar(db_session, [_ext()], AGORA + timedelta(hours=1))

    assert (primeira.criadas, segunda.criadas, segunda.sem_mudanca) == (1, 0, 1)
    assert db_session.query(LicitacaoPublica).count() == 1
    publica = db_session.query(LicitacaoPublica).one()
    assert _eventos(db_session, publica.id) == [("criada", 1)] and publica.versao == 1
    assert publica.ultima_coleta_em == AGORA + timedelta(hours=1)  # só registra que foi visto de novo


def test_retificacao_gera_nova_versao_e_evento_com_antes_e_depois(db_session):
    corpus.registrar(db_session, [_ext()], AGORA)

    r = corpus.registrar(db_session, [_ext(prazo_proposta=datetime(2026, 11, 15), valor_estimado=2500.0, atualizado_externo_em=datetime(2026, 10, 5))], AGORA)

    publica = db_session.query(LicitacaoPublica).one()
    assert r.retificadas == 1 and publica.versao == 2 and publica.valor_estimado == 2500.0
    evento = db_session.query(EventoLicitacaoPublica).filter_by(tipo="retificada").one()
    assert evento.mudancas["valor_estimado"] == [1000.0, 2500.0]
    assert evento.mudancas["prazo_proposta"] == ["2026-11-01T00:00:00", "2026-11-15T00:00:00"]
    assert "titulo" not in evento.mudancas  # só o que mudou


def test_mudanca_de_situacao_tem_evento_proprio_e_fonte_muda_nao_apaga_a_situacao_conhecida(db_session):
    corpus.registrar(db_session, [_ext()], AGORA)

    suspensa = corpus.registrar(db_session, [_ext(situacao_externa="Suspensa", atualizado_externo_em=datetime(2026, 10, 6))], AGORA)
    sem_situacao = corpus.registrar(db_session, [_ext(situacao_externa=None, atualizado_externo_em=datetime(2026, 10, 7))], AGORA)

    publica = db_session.query(LicitacaoPublica).one()
    assert suspensa.situacoes_alteradas == 1 and sem_situacao.sem_mudanca == 1
    assert publica.situacao_externa == "Suspensa"
    assert _eventos(db_session, publica.id) == [("criada", 1), ("situacao_alterada", 2)]


def test_leitura_mais_antiga_nao_desfaz_atualizacao_mais_nova(db_session):
    corpus.registrar(db_session, [_ext(situacao_externa="Anulada", atualizado_externo_em=datetime(2026, 10, 10))], AGORA)

    antiga = corpus.registrar(db_session, [_ext(situacao_externa="Divulgada", atualizado_externo_em=datetime(2026, 10, 2))], AGORA)

    publica = db_session.query(LicitacaoPublica).one()
    assert antiga.obsoletas == 1 and publica.situacao_externa == "Anulada" and publica.versao == 1


def test_uf_e_municipio_preenchem_em_silencio_sem_contar_como_retificacao(db_session):
    corpus.registrar(db_session, [_ext(uf=None, municipio=None, modalidade_codigo=None)], AGORA)

    r = corpus.registrar(db_session, [_ext()], AGORA)

    publica = db_session.query(LicitacaoPublica).one()
    assert (publica.uf, publica.municipio, publica.modalidade_codigo) == ("SP", "Campinas", 6)
    assert r.retificadas == 0 and publica.versao == 1  # a localização não entra no hash


def test_licitacao_manual_nunca_entra_no_corpus(db_session):
    r = corpus.registrar(db_session, [_ext(fonte="MANUAL")], AGORA)

    assert r.mapa == {} and db_session.query(LicitacaoPublica).count() == 0


def test_corrida_na_insercao_termina_com_uma_linha_e_a_sessao_continua_utilizavel(db_session):
    corpus.registrar(db_session, [_ext()], AGORA)
    db_session.commit()

    # Outra coleta inseriu a mesma chave entre o SELECT e o INSERT: `_criar` recebe a violação de unicidade e devolve None.
    assert corpus._criar(db_session, _ext(), corpus._conteudo_da_fonte(_ext()), AGORA) is None

    assert db_session.query(LicitacaoPublica).count() == 1
    assert corpus.registrar(db_session, [_ext(2)], AGORA).criadas == 1  # a transação segue válida depois do savepoint revertido


def test_falha_no_meio_do_lote_e_recuperavel_sem_duplicar(db_session, monkeypatch):
    original = corpus._criar
    chamadas = {"n": 0}

    def quebra_na_segunda(*args, **kwargs):
        chamadas["n"] += 1
        if chamadas["n"] == 2:
            raise RuntimeError("falha simulada")
        return original(*args, **kwargs)

    monkeypatch.setattr(corpus, "_criar", quebra_na_segunda)
    with pytest.raises(RuntimeError):
        corpus.registrar(db_session, [_ext(1), _ext(2), _ext(3)], AGORA)
    db_session.rollback()  # o chamador desfaz a transação inteira
    monkeypatch.setattr(corpus, "_criar", original)

    corpus.registrar(db_session, [_ext(1), _ext(2), _ext(3)], AGORA)
    db_session.commit()

    assert db_session.query(LicitacaoPublica).count() == 3
    assert db_session.query(EventoLicitacaoPublica).filter_by(tipo="criada").count() == 3


def test_o_corpus_so_tem_colunas_publicas():
    """Guarda de esquema: dado privado do tenant (e o próprio tenant) jamais entra nesta tabela."""
    proibidas = {"tenant_id", "conta_id", "oferta_id", "responsavel_usuario_id", "vencedor", "valor_proposta", "motivo_resultado", "concorrentes",
                 "parceiros", "score", "status", "notas", "estrategia", "prazo_esclarecimento"}
    colunas = {c.name for c in LicitacaoPublica.__table__.columns} | {c.name for c in EventoLicitacaoPublica.__table__.columns}
    assert not colunas & proibidas, colunas & proibidas


def test_hash_ignora_localizacao_e_muda_com_o_conteudo():
    base = corpus._conteudo_da_fonte(_ext())
    assert corpus.hash_conteudo(base) == corpus.hash_conteudo(corpus._conteudo_da_fonte(_ext(uf="RJ", municipio="Outra", modalidade_codigo=9)))
    assert corpus.hash_conteudo(base) != corpus.hash_conteudo(corpus._conteudo_da_fonte(_ext(valor_estimado=1.0)))
