"""D-072 em Postgres real (migrado): plano Government da migração, contrato com valores em NUMERIC, pool anual na carteira
(lote com trava de linha), comissão por recebimento e renovação. Roda quando `B2BON_TESTE_PG_URL` aponta para um Postgres
migrado."""

import os
import uuid
from datetime import date

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.contexts.finops import contract as finops
from app.contexts.governo import contract as governo
from app.models.comissao_representante import ComissaoRepresentante
from app.models.plano import Plano
from app.models.representante import Representante
from app.services import comissao_service

URL = os.environ.get("B2BON_TESTE_PG_URL")
pytestmark = pytest.mark.skipif(not URL, reason="B2BON_TESTE_PG_URL não definido (Postgres migrado)")


def test_contrato_governo_no_postgres():
    engine = create_engine(URL)
    tenant = f"pg-gov-{uuid.uuid4().hex[:8]}"
    with engine.begin() as conexao:
        conexao.execute(text("INSERT INTO tenant (id, razao_social) VALUES (:t, :t)"), {"t": tenant})
    Sessao = sessionmaker(bind=engine)
    with Sessao() as db:
        plano = db.query(Plano).filter_by(nome="B2B ON Government Professional").one()  # criado pela migração
        rep = Representante(nome="PG", email=f"{tenant}@rep.com", chave_pix="pix", percentual_comissao=0.1)
        db.add(rep)
        db.commit()
        comissao_service.definir(db, 0.15, 0.05, "PG", "teste")
        contrato = governo.contratos.criar(db, tenant_id=tenant, plano_id=plano.id, modelo=plano.modelo_cobranca, referencia_contrato="PG-1",
                                           entidade_governamental="Órgão PG", assinado_em=date.today(), representante_id=rep.id)
        assert float(finops.carteira.disponivel(db, tenant)) == 600_000
        licenca = next(c for c in governo.contratos.componentes(db, contrato) if c.tipo == "LICENSE")
        governo.recebimentos.registrar(db, contrato.id, componente_id=licenca.id, valor=40_000, recebido_em=date.today())
        governo.contratos.renovar(db, contrato.id, valor_assinatura=37_800, motivo_reajuste="Cláusula de reajuste")
        valores = [c.valor_comissao for c in db.query(ComissaoRepresentante).filter_by(contrato_governo_id=contrato.id)]
        assert valores == [6_400.0]  # (40.000 − 15% − 5%) × 20%
        metricas = governo.analytics.metricas(db, tenant_id=tenant)
        assert (metricas["bookings"]["licenca"], metricas["renewal_arr"], metricas["cash_in"]) == (120_000, 37_800, 40_000)
