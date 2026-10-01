"""Exclusão definitiva de tenant em Postgres real (FKs aplicadas): o caso de produção do revendedor desligado cujo
vendedor ainda era responsável por uma conta do distribuidor (`fk_conta_vendedor_usuario_id` → HTTP 500) e o tenant
que já pagou (FK de `pagamento_licenca`). Roda quando `B2BON_TESTE_PG_URL` aponta para um Postgres migrado."""

import os
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.conta import Conta
from app.models.pagamento_licenca import PagamentoLicenca
from app.models.plano import Plano
from app.models.redefinicao_senha import RedefinicaoSenha
from app.models.tenant import Tenant
from app.models.usuario import Usuario
from app.services import tenant_service

URL = os.environ.get("B2BON_TESTE_PG_URL")
pytestmark = pytest.mark.skipif(not URL, reason="B2BON_TESTE_PG_URL não definido (Postgres migrado)")


def test_exclui_revendedor_com_vendedor_em_conta_do_distribuidor_e_pagamento():
    sufixo = uuid.uuid4().hex[:8]
    pai, filho = f"pg-dist-{sufixo}", f"pg-rev-{sufixo}"
    Sessao = sessionmaker(bind=create_engine(URL))
    with Sessao() as db:
        db.add(Tenant(id=pai, razao_social="Distribuidor PG"))
        db.flush()
        db.add(Tenant(id=filho, razao_social="Revendedor PG", tenant_pai_id=pai, ativo=False))
        db.flush()
        ator = Usuario(tenant_id=pai, nome="Gestor", email=f"g-{sufixo}@pg.com", papel="admin", ativo=True)
        vendedora = Usuario(tenant_id=filho, nome="Vendedora", email=f"v-{sufixo}@pg.com", papel="admin", ativo=False)
        db.add_all([ator, vendedora])
        db.flush()
        conta = Conta(tenant_id=pai, nome="Conta do distribuidor", status="prospectada", vendedor_usuario_id=vendedora.id)
        plano = db.query(Plano).filter_by(nome="Bid Intelligence").one()
        db.add_all([
            conta,
            PagamentoLicenca(tenant_id=filho, plano_id=plano.id, preferencia_id_externo=f"pg-{sufixo}", status="aprovado", valor=1.0),
            RedefinicaoSenha(usuario_id=vendedora.id, token=f"t-{sufixo}", validade_em=datetime.now(UTC)),
        ])
        db.commit()

        tenant_service.excluir_definitivamente(db, filho, ator)

        db.expire_all()
        assert db.get(Tenant, filho) is None
        assert db.get(Conta, conta.id).vendedor_usuario_id is None
        assert db.query(PagamentoLicenca).filter_by(tenant_id=filho).count() == 1  # retenção fiscal
