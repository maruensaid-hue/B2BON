"""Mecanismo de contexto de RLS (D-110), sem banco PostgreSQL: o que a sessão guarda e quando o evento `after_begin` grava as variáveis.

O enforcement de verdade (políticas negando linhas) é provado em `tests/integration/test_rls_postgres.py`, que exige PostgreSQL.
"""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import rls, rls_registro


@pytest.fixture()
def emissoes(monkeypatch):
    """Faz o `after_begin` agir como no PostgreSQL e guarda o que ele gravaria, em vez de executar `set_config`."""
    emitidas: list[rls.ContextoRls] = []
    monkeypatch.setattr(rls, "_eh_postgres", lambda conexao: True)
    monkeypatch.setattr(rls, "_emitir", lambda conexao, contexto: emitidas.append(contexto))
    return emitidas


@pytest.fixture()
def sessao():
    motor = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with Session(motor) as s:
        yield s
    motor.dispose()


def test_sem_contexto_nada_e_gravado(sessao, emissoes):
    sessao.execute(text("select 1"))
    assert emissoes == []  # variável ausente: as políticas negam


def test_contexto_de_tenant_e_gravado_ao_iniciar_a_transacao(sessao, emissoes):
    rls.definir_tenant(sessao, "t-a")
    sessao.execute(text("select 1"))
    assert [(c.tenant_id, c.escopo) for c in emissoes] == [("t-a", "tenant")]


def test_contexto_e_regravado_em_cada_transacao_depois_de_commit_e_de_rollback(sessao, emissoes):
    """O `SET LOCAL` some no fim da transação; a sessão abre outra e o evento precisa gravar de novo, senão a segunda transação ficaria sem contexto."""
    rls.definir_tenant(sessao, "t-a")
    sessao.execute(text("select 1"))
    sessao.commit()
    sessao.execute(text("select 1"))
    sessao.rollback()
    sessao.execute(text("select 1"))
    assert [c.tenant_id for c in emissoes] == ["t-a", "t-a", "t-a"]


def test_trocar_o_contexto_com_transacao_aberta_vale_na_hora(sessao, emissoes):
    sessao.execute(text("select 1"))  # abre a transação ainda sem contexto
    rls.definir_tenant(sessao, "t-a")
    assert [c.tenant_id for c in emissoes] == ["t-a"]


def test_contexto_tenant_restaura_o_anterior_inclusive_em_erro(sessao, emissoes):
    rls.definir_tenant(sessao, "t-a")
    with pytest.raises(RuntimeError), rls.contexto_tenant(sessao, "t-b"):
        assert rls.contexto_atual(sessao).tenant_id == "t-b"
        raise RuntimeError("falha no meio da volta")
    assert rls.contexto_atual(sessao).tenant_id == "t-a"


def test_tenant_vazio_e_recusado():
    with pytest.raises(ValueError):
        rls.definir_tenant(Session(), "")


def test_sistema_e_busca_so_aceitam_nomes_registrados(sessao):
    with pytest.raises(ValueError):
        with rls.contexto_sistema(sessao, "inventado"):
            pass
    with pytest.raises(ValueError):
        with rls.contexto_busca(sessao, "inventado", "x"):
            pass
    for nome in rls_registro.CONTEXTOS_SISTEMA:
        with rls.contexto_sistema(sessao, nome):
            assert rls.contexto_atual(sessao).escopo == f"sistema:{nome}"


def test_ampliar_leitura_so_vale_em_contexto_de_tenant(sessao, emissoes):
    rls.ampliar_leitura(sessao, ["t-a", "t-filho"])  # sem contexto: não faz nada (o banco continua negando)
    assert rls.contexto_atual(sessao).vazio
    rls.definir_tenant(sessao, "t-pai")
    rls.ampliar_leitura(sessao, ["t-filho", "t-pai", "t-filho"])
    assert rls.contexto_atual(sessao).visiveis == ("t-filho", "t-pai")
    assert rls.contexto_atual(sessao).tenant_id == "t-pai"  # a escrita segue no tenant do usuário


def test_sessao_irma_nasce_com_o_mesmo_contexto(sessao):
    rls.definir_tenant(sessao, "t-a")
    irma = rls.sessao_irma(sessao)
    try:
        assert rls.contexto_atual(irma).tenant_id == "t-a"
    finally:
        irma.close()
    rls.limpar(sessao)
    outra = rls.sessao_irma(sessao)
    try:
        assert rls.contexto_atual(outra).vazio
    finally:
        outra.close()


def test_trocar_de_contexto_grava_antes_o_que_estava_pendente(sessao):
    """O autoflush é desligado na aplicação; sem este flush o pendente seria gravado depois, sob outro contexto, e o WITH CHECK o recusaria."""
    sessao.execute(text("create table item (id integer primary key, dono text)"))
    sessao.execute(text("insert into item (id, dono) values (1, 'a')"))
    rls.definir_tenant(sessao, "t-a")
    rls.definir_tenant(sessao, "t-b")  # não pode perder nem reordenar nada
    assert sessao.execute(text("select count(*) from item")).scalar() == 1
