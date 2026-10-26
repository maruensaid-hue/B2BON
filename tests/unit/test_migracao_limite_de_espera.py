import pytest

from app.db.migracao import LIMITE_DE_ESPERA_PADRAO, comando_limite_de_espera


def test_postgres_ganha_limite_de_espera_por_bloqueio_so_na_transacao_da_migracao(monkeypatch):
    monkeypatch.delenv("ALEMBIC_LOCK_TIMEOUT", raising=False)
    assert comando_limite_de_espera("postgresql") == f"SET LOCAL lock_timeout = '{LIMITE_DE_ESPERA_PADRAO}'"


def test_sqlite_nao_recebe_comando(monkeypatch):
    monkeypatch.delenv("ALEMBIC_LOCK_TIMEOUT", raising=False)
    assert comando_limite_de_espera("sqlite") is None


def test_limite_pode_ser_ajustado_por_variavel_de_ambiente(monkeypatch):
    monkeypatch.setenv("ALEMBIC_LOCK_TIMEOUT", "90s")
    assert comando_limite_de_espera("postgresql") == "SET LOCAL lock_timeout = '90s'"


@pytest.mark.parametrize("invalido", ["30", "abc", "30s; DROP TABLE x", "-1s", ""])
def test_valor_invalido_e_recusado_em_vez_de_virar_sql(monkeypatch, invalido):
    monkeypatch.setenv("ALEMBIC_LOCK_TIMEOUT", invalido)
    with pytest.raises(ValueError):
        comando_limite_de_espera("postgresql")
