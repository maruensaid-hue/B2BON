"""D-082 em Postgres real (migrado): a demonstração é semeada e depois apagada por inteiro — no Postgres as FKs são
verificadas de verdade, então a varredura em ordem topológica tem de apagar cada tabela antes da tabela-pai. Roda
quando `B2BON_TESTE_PG_URL` aponta para um Postgres migrado."""

import os
from datetime import timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.conta import Conta
from app.models.licitacao import Licitacao
from app.models.tenant import Tenant
from app.services.demo import sessao

URL = os.environ.get("B2BON_TESTE_PG_URL")
pytestmark = pytest.mark.skipif(not URL, reason="B2BON_TESTE_PG_URL não definido (Postgres migrado)")


def test_demonstracao_semeada_e_apagada_no_postgres(monkeypatch):
    monkeypatch.setattr(settings, "demo_habilitada", True)
    Sessao = sessionmaker(bind=create_engine(URL))
    with Sessao() as db:
        usuario, _ = sessao.criar(db)
        tenant_id = usuario.tenant_id
        assert db.query(Conta).filter_by(tenant_id=tenant_id).count() == 15
        assert db.query(Licitacao).filter_by(tenant_id=tenant_id).count() == 7
        tenant = db.get(Tenant, tenant_id)
        tenant.demo_expira_em = tenant.demo_expira_em - timedelta(hours=settings.demo_ttl_horas + 1)
        db.commit()
        assert sessao.purgar_expiradas(db, limite=50) >= 1
        db.expire_all()
        assert db.get(Tenant, tenant_id) is None and db.query(Conta).filter_by(tenant_id=tenant_id).count() == 0
