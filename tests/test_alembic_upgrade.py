"""Fase 7B, hardening — rede de segurança que faltava: nenhum teste
validava `alembic upgrade head` de verdade (a suíte cria schema via
`Base.metadata.create_all()`, que nunca roda SQL de migração). Um erro
de SQL específico de dialeto (ex.: `sa.text('now()')` em vez de
`sa.func.now()` — bug real cometido e corrigido manualmente na Fase 6A
desta sessão) só aparecia rodando `alembic upgrade head` à mão contra
SQLite/Postgres, nunca no CI. Este teste roda a migração de verdade
contra um SQLite temporário isolado (engine próprio, não o `engine`
global da aplicação) a cada execução da suíte."""

import os
import tempfile

from alembic import command
from alembic.config import Config

from app.core.config import settings


def test_alembic_upgrade_head_roda_sem_erro(monkeypatch):
    fd, caminho_db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(caminho_db)  # o próprio SQLite/alembic recria o arquivo

    monkeypatch.setattr(settings, "database_url", f"sqlite:///{caminho_db}")
    try:
        config = Config("alembic.ini")
        command.upgrade(config, "head")
    finally:
        if os.path.exists(caminho_db):
            os.remove(caminho_db)


def test_migracao_fase15_preserva_saldo_legado_e_reconcilia(monkeypatch):
    """Fase 15 §56: saldo da carteira da Fase 5 vira lote ADJUSTMENT com o
    mesmo valor; histórico antigo intacto; reconciliação consistente."""
    import sqlalchemy as sa
    from sqlalchemy.orm import Session

    from app.contexts.finops import carteira

    fd, caminho_db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(caminho_db)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{caminho_db}")
    engine = sa.create_engine(f"sqlite:///{caminho_db}")
    try:
        config = Config("alembic.ini")
        command.upgrade(config, "c4f1a9e7d2b3")
        with engine.begin() as conexao:
            for tenant_id, saldo in (("t-migr-a", 1234.5), ("t-migr-b", 0)):
                conexao.execute(sa.text("INSERT INTO tenant (id, razao_social) VALUES (:t, :t)"), {"t": tenant_id})
                conexao.execute(sa.text("INSERT INTO carteira_creditos (tenant_id, saldo) VALUES (:t, :s)"), {"t": tenant_id, "s": saldo})
            conexao.execute(sa.text("INSERT INTO movimento_credito (tenant_id, tipo, quantidade, saldo_apos, descricao) "
                                    "VALUES ('t-migr-a', 'ALOCACAO', 1234.5, 1234.5, 'legado')"))
        command.upgrade(config, "head")
        with Session(engine) as db:
            lotes = db.execute(sa.text("SELECT tenant_id, tipo, quantidade_restante FROM lote_credito")).fetchall()
            assert [(t, tipo, float(q)) for t, tipo, q in lotes] == [("t-migr-a", "ADJUSTMENT", 1234.5)]
            assert db.execute(sa.text("SELECT count(*) FROM movimento_credito WHERE tipo = 'ALOCACAO'")).scalar() == 1
            relatorio = carteira.reconciliar(db, "t-migr-a")
            assert relatorio["consistente"] and relatorio["disponivel"] == 1234.5
            assert carteira.reconciliar(db, "t-migr-b")["consistente"]
    finally:
        engine.dispose()
        if os.path.exists(caminho_db):
            os.remove(caminho_db)


def test_s3_tabelas_unificadas_backfill_sobre_dados_anteriores(monkeypatch):
    """Sourcing S3: dados criados antes da migração chegam às tabelas
    unificadas pelo backfill, com paridade conferida pela leitura dupla
    estrita, e o trigger da migração impede mudar o lado."""
    import pytest
    import sqlalchemy as sa
    from sqlalchemy.orm import Session

    import app.contexts.bids.contract  # noqa: F401 — registra o espelho do vendedor
    import app.contexts.procurement.contract  # noqa: F401 — e o do comprador
    from app.contexts.bids import contract as bids
    from app.contexts.procurement.repositorio import COMPRA
    from app.contexts.sourcing import contract as sourcing

    fd, caminho_db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(caminho_db)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{caminho_db}")
    engine = sa.create_engine(f"sqlite:///{caminho_db}")
    try:
        config = Config("alembic.ini")
        command.upgrade(config, "e7b3c1a9f5d2")
        with engine.begin() as conexao:
            conexao.execute(sa.text("INSERT INTO tenant (id, razao_social) VALUES ('t-s3', 't')"))
            conexao.execute(sa.text(
                "INSERT INTO licitacao (id, tenant_id, titulo, modalidade, fonte, status) "
                "VALUES (1, 't-s3', 'Edital antigo', 'PUBLIC_TENDER', 'MANUAL', 'IDENTIFICADA')"))
            conexao.execute(sa.text(
                "INSERT INTO documento_licitacao (tenant_id, licitacao_id, tipo, nome_arquivo, tipo_mime, tamanho_bytes, sha256, "
                "paginas, fonte, status_analise) VALUES ('t-s3', 1, 'EDITAL', 'e.pdf', 'application/pdf', 10, 'abc', 2, 'UPLOAD', 'PENDENTE')"))
            conexao.execute(sa.text(
                "INSERT INTO processo_contratacao (id, tenant_id, orgao_id, objeto, status, valor_sigiloso) "
                "VALUES (1, 't-s3', 1, 'Compra antiga', 'PLANEJAMENTO', 0)"))
        command.upgrade(config, "head")
        with Session(engine) as db:
            assert db.execute(sa.text("SELECT count(*) FROM processo_sourcing")).scalar() == 0  # expand não copia sozinho
            relatorio = sourcing.espelho.sincronizar_todos(db)
            assert relatorio["SELL"]["licitacao"]["espelhados"] == 1 and relatorio["BUY"]["processo_contratacao"]["espelhados"] == 1
            assert bids.repositorio.VENDA.obter_processo(db, "t-s3", 1).titulo == "Edital antigo"  # leitura dupla ESTRITA
            assert [d.tipo for d in bids.repositorio.VENDA.documentos(db, "t-s3", 1)] == ["EDITAL"]
            assert COMPRA.obter_processo(db, "t-s3", 1).objeto == "Compra antiga"
            with pytest.raises(sa.exc.IntegrityError):
                db.execute(sa.text("UPDATE processo_sourcing SET lado = 'BUY' WHERE origem_tabela = 'licitacao'"))
    finally:
        engine.dispose()
        if os.path.exists(caminho_db):
            os.remove(caminho_db)


def test_phase_b_obrigatorio_nulo_para_requisito_anterior_e_trigger_preservado(monkeypatch):
    """Phase B: requisito anterior fica UNKNOWN (nulo), a leitura dupla estrita
    continua batendo e o trigger de lado de `requisito_sourcing` sobrevive ao
    upgrade e ao downgrade (ADD/DROP COLUMN sem recriar a tabela)."""
    import pytest
    import sqlalchemy as sa
    from sqlalchemy.orm import Session

    import app.contexts.bids.contract  # noqa: F401 — registra o espelho do vendedor
    from app.contexts.bids import contract as bids
    from app.contexts.sourcing import contract as sourcing

    fd, caminho_db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(caminho_db)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{caminho_db}")
    engine = sa.create_engine(f"sqlite:///{caminho_db}")

    def lado_imutavel():
        with engine.begin() as conexao, pytest.raises(sa.exc.IntegrityError):
            conexao.execute(sa.text("UPDATE requisito_sourcing SET lado = 'BUY'"))

    try:
        config = Config("alembic.ini")
        command.upgrade(config, "a3d5f7b9c1e2")
        with engine.begin() as conexao:
            conexao.execute(sa.text("INSERT INTO tenant (id, razao_social) VALUES ('t-b', 't')"))
            conexao.execute(sa.text("INSERT INTO licitacao (id, tenant_id, titulo, modalidade, fonte, status) "
                                    "VALUES (1, 't-b', 'Edital', 'PUBLIC_TENDER', 'MANUAL', 'IDENTIFICADA')"))
            conexao.execute(sa.text("INSERT INTO requisito_licitacao (tenant_id, licitacao_id, categoria, descricao, evidencia, origem, "
                                    "status) VALUES ('t-b', 1, 'HABILITACAO', 'CND', 'deverá apresentar CND', 'manual', 'confirmado')"))
        command.upgrade(config, "head")
        with Session(engine) as db:
            sourcing.espelho.sincronizar_todos(db)
            requisito, = bids.repositorio.VENDA.requisitos(db, "t-b", 1)  # leitura dupla ESTRITA
            assert requisito.obrigatorio is None  # nada inferido retroativamente
        lado_imutavel()
        command.downgrade(config, "a3d5f7b9c1e2")
        lado_imutavel()
    finally:
        engine.dispose()
        if os.path.exists(caminho_db):
            os.remove(caminho_db)
