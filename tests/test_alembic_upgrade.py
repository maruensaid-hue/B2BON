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
