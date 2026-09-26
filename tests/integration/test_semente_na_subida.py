"""Phase H (TD-091): o catálogo de AI Credits é semeado na subida, não na primeira leitura pública."""

from sqlalchemy.orm import sessionmaker

import app.main as principal
from app.models.creditos_ia import CatalogoCreditos, PacoteCreditos


def test_subida_semeia_o_catalogo_uma_vez(db_session, monkeypatch):
    monkeypatch.setattr(principal, "SessionLocal", sessionmaker(bind=db_session.get_bind()))
    assert db_session.query(CatalogoCreditos).count() == 0
    principal.semear_catalogos()
    principal.semear_catalogos()  # idempotente
    assert db_session.query(CatalogoCreditos).count() == 1 and db_session.query(PacoteCreditos).count() > 0


def test_falha_na_semente_nao_impede_a_subida(monkeypatch, caplog):
    def quebrado():
        raise RuntimeError("banco sem migração")

    monkeypatch.setattr(principal, "SessionLocal", quebrado)
    principal.semear_catalogos()
    assert "CATALOGO_SEMENTE_NA_SUBIDA_FALHOU" in caplog.text
