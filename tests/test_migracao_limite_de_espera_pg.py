"""PostgreSQL de verdade (job `postgres-migrations` do CI): com a tabela em uso por outro processo, a migração falha rápido em vez de pendurar."""

import os
import time

import pytest
import sqlalchemy as sa

from app.db.migracao import comando_limite_de_espera

URL = os.environ.get("B2BON_TESTE_PG_URL")
pytestmark = pytest.mark.skipif(not URL, reason="exige PostgreSQL (B2BON_TESTE_PG_URL)")


def test_alter_table_bloqueado_falha_em_segundos(monkeypatch):
    monkeypatch.setenv("ALEMBIC_LOCK_TIMEOUT", "1s")
    engine = sa.create_engine(URL)
    try:
        with engine.begin() as con:
            con.exec_driver_sql("DROP TABLE IF EXISTS teste_limite_espera")
            con.exec_driver_sql("CREATE TABLE teste_limite_espera (id integer)")
        with engine.connect() as processo_em_uso, engine.connect() as migracao:
            processo_em_uso.exec_driver_sql("SELECT * FROM teste_limite_espera")  # transação aberta usando a tabela, como o envio longo
            inicio = time.monotonic()
            with pytest.raises(sa.exc.OperationalError, match="lock timeout"):
                with migracao.begin():
                    migracao.exec_driver_sql(comando_limite_de_espera("postgresql"))
                    migracao.exec_driver_sql("ALTER TABLE teste_limite_espera ADD COLUMN nova integer")
            assert time.monotonic() - inicio < 10
            processo_em_uso.rollback()
    finally:
        with engine.begin() as con:
            con.exec_driver_sql("DROP TABLE IF EXISTS teste_limite_espera")
        engine.dispose()
