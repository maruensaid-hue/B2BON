"""D-080 em Postgres real (migrado): quotas e políticas da migração e as agregações do MAP Performance (CASE, subconsultas
agrupadas, junções com o CRM) executadas no Postgres. Roda quando `B2BON_TESTE_PG_URL` aponta para um Postgres migrado."""

import os
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.contexts.map.performance import painel
from app.models.atividade import Atividade
from app.models.conta import Conta
from app.models.decisor import Decisor
from app.models.estagio_funil import EstagioFunil
from app.models.negocio import Negocio
from app.models.pagamento_licenca import PagamentoLicenca
from app.models.plano import Plano
from app.models.representante import Representante
from app.models.tenant import Tenant
from app.models.usuario import Usuario

URL = os.environ.get("B2BON_TESTE_PG_URL")
pytestmark = pytest.mark.skipif(not URL, reason="B2BON_TESTE_PG_URL não definido (Postgres migrado)")


def test_painel_map_performance_no_postgres():
    sufixo = uuid.uuid4().hex[:8]
    hoje = datetime.now(UTC).date()
    competencia, agora = hoje.strftime("%Y-%m"), datetime.combine(hoje, datetime.min.time())
    Sessao = sessionmaker(bind=create_engine(URL))
    with Sessao() as db:
        operador, cliente = f"pg-op-{sufixo}", f"pg-cli-{sufixo}"
        db.add_all([Tenant(id=operador, razao_social="Operador PG")])
        db.flush()
        usuario = Usuario(tenant_id=operador, nome="Rep PG", email=f"rep-{sufixo}@pg.com", papel="user", ativo=True)
        db.add(usuario)
        db.flush()
        rep = Representante(nome="Rep PG", email=f"r-{sufixo}@pg.com", chave_pix="pix", percentual_comissao=0.2, usuario_id=usuario.id)
        db.add(rep)
        db.flush()
        plano = db.query(Plano).filter_by(nome="Bid Intelligence").one()  # criado pelas migrações
        db.add(Tenant(id=cliente, razao_social="Cliente PG", representante_id=rep.id))
        db.flush()
        db.add(PagamentoLicenca(tenant_id=cliente, plano_id=plano.id, preferencia_id_externo=f"pg-{sufixo}", status="aprovado",
                                valor=1490.0, confirmado_em=agora))
        estagio = EstagioFunil(tenant_id=operador, nome="Descoberta", ordem=1, tipo="aberto")
        conta = Conta(tenant_id=operador, nome="Conta PG", status="prospectada", score_aderencia=0.9)
        db.add_all([estagio, conta])
        db.flush()
        db.add_all([Decisor(tenant_id=operador, conta_id=conta.id, nome="Decisor"),
                    Atividade(tenant_id=operador, conta_id=conta.id, usuario_id=usuario.id, tipo="ligacao", descricao="x", criado_em=agora),
                    Negocio(tenant_id=operador, conta_id=conta.id, vendedor_usuario_id=usuario.id, estagio_id=estagio.id, nome="N",
                            valor=6000.0, probabilidade=50, origem="manual", criado_em=agora - timedelta(days=1))])
        db.flush()
        resultado = painel.calcular(db, [rep], competencia, hoje)["paineis"][0]
        quotas = {"2026-10": 7500, "2026-11": 10000, "2026-12": 12500, "2027-01": 15000, "2027-02": 17500, "2027-03": 20000}
        assert resultado["quota"] == quotas.get(competencia)  # quota padrão semeada pela migração
        assert resultado["realizado_new_mrr"] == 1490.0 and resultado["mix"]["por_familia"]["BID_INTELLIGENCE"]["valor"] == 1490.0
        assert resultado["pipeline"]["qualificado_mrr"] == 6000.0
        assert (resultado["funil_mes"]["contas_trabalhadas"], resultado["funil_mes"]["contatos_efetivos"]) == (1, 1)
        db.rollback()
