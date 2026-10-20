"""As quatro migrações da V5.x sobre dados da versão anterior: preservam o que existia, criam o novo com os defaults certos e o ciclo
downgrade → upgrade funciona (com a perda de dados documentada abaixo).

Roda sempre em SQLite temporário. Com `B2BON_TESTE_PG_MIGRACAO_URL` (um PostgreSQL de teste, já migrado ou vazio, DESCARTÁVEL), roda também nele: o job
`postgres-migrations` do CI usa isso. NUNCA aponte para um banco compartilhado: o teste faz downgrade e reescreve o schema.

Efeito dos downgrades (perda de dados, por migração — o conteúdo é re-coletável, o histórico não):
- b8e0a2c4d6f8: apaga `coleta_site_conta` e `indicador_financeiro_conta` (histórico de coletas de site e indicadores);
- a7d9f1b3c5e7: apaga `configuracao_coleta_fonte` e `execucao_coleta_fonte` (configuração e histórico da coleta PNCP);
- f6c8e0a2b4d6: apaga `conteudo_pagina_site` (texto das páginas; basta coletar de novo);
- e5b7d9f1a3c5: remove `tentativas` e `proxima_tentativa_em` da fila de enriquecimento (as linhas da fila permanecem)."""

import os
import tempfile

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from app.core.config import settings

ANTERIOR = "d2e4f6a8b0c2"  # head antes da V5.x
NOVAS_TABELAS = ("conteudo_pagina_site", "configuracao_coleta_fonte", "execucao_coleta_fonte", "coleta_site_conta", "indicador_financeiro_conta")
PG_URL = os.environ.get("B2BON_TESTE_PG_MIGRACAO_URL")


def _urls():
    yield pytest.param("sqlite", id="sqlite")
    yield pytest.param("postgres", id="postgres", marks=pytest.mark.skipif(not PG_URL, reason="B2BON_TESTE_PG_MIGRACAO_URL não definido"))


def _tabelas(engine) -> set[str]:
    return set(sa.inspect(engine).get_table_names())


def _colunas(engine, tabela: str) -> set[str]:
    return {c["name"] for c in sa.inspect(engine).get_columns(tabela)}


@pytest.fixture(params=list(_urls()))
def ambiente(request, monkeypatch):
    if request.param == "postgres":
        url, caminho = PG_URL, None
    else:
        fd, caminho = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.remove(caminho)
        url = f"sqlite:///{caminho}"
    monkeypatch.setattr(settings, "database_url", url)
    engine = sa.create_engine(url)
    config = Config("alembic.ini")
    if request.param == "postgres":
        command.upgrade(config, "head")  # garante o ponto de partida; depois o teste volta para a versão anterior
    yield engine, config
    engine.dispose()
    if caminho and os.path.exists(caminho):
        os.remove(caminho)


def _semear_dados_anteriores(engine) -> None:
    with engine.begin() as con:
        con.execute(sa.text("DELETE FROM fila_enriquecimento_conta"))
        con.execute(sa.text("DELETE FROM conta WHERE tenant_id = 't-migr-v5'"))  # idempotente: o PostgreSQL de CI persiste entre os testes
        con.execute(sa.text("INSERT INTO tenant (id, razao_social) VALUES ('t-migr-v5', 'Migração V5') ON CONFLICT (id) DO NOTHING")
                    if engine.dialect.name == "postgresql" else
                    sa.text("INSERT OR IGNORE INTO tenant (id, razao_social) VALUES ('t-migr-v5', 'Migração V5')"))
        conta_id = con.execute(sa.text("INSERT INTO conta (tenant_id, nome, status) VALUES ('t-migr-v5', 'Conta Legada', 'prospectada') RETURNING id")).scalar()
        for status in ("pendente", "concluido"):
            con.execute(sa.text("INSERT INTO fila_enriquecimento_conta (tenant_id, conta_id, status) VALUES ('t-migr-v5', :c, :s)"), {"c": conta_id, "s": status})


def test_upgrade_sobre_dados_anteriores_preserva_e_cria_com_os_defaults_certos(ambiente):
    engine, config = ambiente
    command.downgrade(config, ANTERIOR) if PG_URL and engine.dialect.name == "postgresql" else command.upgrade(config, ANTERIOR)
    assert not set(NOVAS_TABELAS) & _tabelas(engine)
    assert not {"tentativas", "proxima_tentativa_em"} & _colunas(engine, "fila_enriquecimento_conta")
    _semear_dados_anteriores(engine)

    command.upgrade(config, "head")

    assert set(NOVAS_TABELAS) <= _tabelas(engine)
    with engine.connect() as con:
        linhas = con.execute(sa.text("SELECT status, tentativas, proxima_tentativa_em FROM fila_enriquecimento_conta ORDER BY id")).fetchall()
        assert [(s, t, p) for s, t, p in linhas] == [("pendente", 0, None), ("concluido", 0, None)]  # nada perdido, defaults aplicados
        assert con.execute(sa.text("SELECT count(*) FROM conta WHERE nome = 'Conta Legada'")).scalar() == 1
        for tabela in NOVAS_TABELAS:
            assert con.execute(sa.text(f"SELECT count(*) FROM {tabela}")).scalar() == 0


def test_indice_unico_parcial_impede_duas_coletas_em_andamento_no_banco(ambiente):
    engine, config = ambiente
    command.upgrade(config, "head")
    with engine.begin() as con:
        con.execute(sa.text("INSERT INTO tenant (id, razao_social) VALUES ('t-idx-v5', 'Idx')") if engine.dialect.name == "sqlite" else
                    sa.text("INSERT INTO tenant (id, razao_social) VALUES ('t-idx-v5', 'Idx') ON CONFLICT (id) DO NOTHING"))
        con.execute(sa.text("DELETE FROM execucao_coleta_fonte WHERE tenant_id = 't-idx-v5'"))
        inserir = ("INSERT INTO execucao_coleta_fonte (tenant_id, fonte, disparo, estado, iniciada_em, consultados, inseridos, atualizados, ignorados, paginas, tentativas) "
                   "VALUES ('t-idx-v5', 'PNCP', 'agendado', :estado, '2026-10-20 12:00:00', 0, 0, 0, 0, 0, 0)")
        con.execute(sa.text(inserir), {"estado": "concluida"})
        con.execute(sa.text(inserir), {"estado": "concluida"})  # várias concluídas: permitido
        con.execute(sa.text(inserir), {"estado": "em_andamento"})
    with pytest.raises(sa.exc.IntegrityError), engine.begin() as con:
        con.execute(sa.text(inserir), {"estado": "em_andamento"})  # a segunda em andamento do mesmo tenant+fonte: recusada pelo banco


def test_ciclo_downgrade_upgrade_funciona_e_so_perde_o_que_esta_documentado(ambiente):
    engine, config = ambiente
    command.upgrade(config, "head")
    _semear_dados_anteriores(engine)
    with engine.begin() as con:
        con.execute(sa.text("UPDATE fila_enriquecimento_conta SET tentativas = 3 WHERE status = 'pendente'"))
        conta_id = con.execute(sa.text("SELECT id FROM conta WHERE nome = 'Conta Legada'")).scalar()
        con.execute(sa.text("INSERT INTO conteudo_pagina_site (tenant_id, conta_id, url, conteudo) VALUES ('t-migr-v5', :c, 'https://x.com', 'texto')"), {"c": conta_id})

    command.downgrade(config, ANTERIOR)

    assert not set(NOVAS_TABELAS) & _tabelas(engine)  # conteúdo e históricos novos foram apagados (documentado no topo deste arquivo)
    assert not {"tentativas", "proxima_tentativa_em"} & _colunas(engine, "fila_enriquecimento_conta")
    with engine.connect() as con:  # o que já existia antes da V5.x continua
        assert con.execute(sa.text("SELECT count(*) FROM fila_enriquecimento_conta")).scalar() == 2
        assert con.execute(sa.text("SELECT count(*) FROM conta WHERE nome = 'Conta Legada'")).scalar() == 1

    command.upgrade(config, "head")
    assert set(NOVAS_TABELAS) <= _tabelas(engine)
    with engine.connect() as con:
        assert [t for (t,) in con.execute(sa.text("SELECT tentativas FROM fila_enriquecimento_conta"))] == [0, 0]  # contador volta ao default
