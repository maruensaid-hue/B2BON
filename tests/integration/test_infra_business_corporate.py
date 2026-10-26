"""D-105: o custo de infraestrutura de Business é o do Enterprise + 30% e o de Corporate é o do Enterprise + 40%. O peso de cada plano vem do
`tier_infraestrutura` na política versionada; a migração publica a versão nova sem perder o que um administrador já tinha ajustado."""

import json
import logging
import os
import tempfile
from datetime import date
from decimal import Decimal

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from app.contexts.comissoes import contract as comissoes
from app.core.config import settings
from app.models.licenca import Licenca
from app.models.plano import Plano
from app.models.tenant import Tenant
from tests.parametros_comissao import componente


@pytest.fixture(autouse=True)
def _preserva_logging():
    """O env.py do Alembic chama `fileConfig`, que desativa os loggers existentes e troca os handlers; sem restaurar, os testes seguintes que
    inspecionam logs (caplog) deixam de enxergá-los."""
    raiz = logging.getLogger()
    handlers, nivel = list(raiz.handlers), raiz.level
    desativados = {n: lg.disabled for n, lg in logging.root.manager.loggerDict.items() if isinstance(lg, logging.Logger)}
    yield
    raiz.handlers[:], raiz.level = handlers, nivel
    for nome, desativado in desativados.items():
        logging.getLogger(nome).disabled = desativado


TENANTS = {"t-ent": "ENTERPRISE", "t-biz": "BUSINESS", "t-corp": "CORPORATE"}


def test_custo_de_business_e_corporate_e_30_e_40_por_cento_acima_do_enterprise(db_session):
    for tenant_id, tier in TENANTS.items():
        plano = Plano(nome=f"Plano {tier}", franquia_contas_mes=0, preco_mensal=1000.0, modulos_contratados=["crm"], tier_infraestrutura=tier)
        db_session.add_all([plano, Tenant(id=tenant_id, razao_social=tier)])
        db_session.flush()
        db_session.add(Licenca(tenant_id=tenant_id, plano_id=plano.id, status="ativa"))
    comissoes.infraestrutura.criar(db_session, componente(1480.0), "teste")
    db_session.commit()

    dados = comissoes.infraestrutura.pool(db_session, date.today())
    assert dados["unidades"] == Decimal("14.8")  # 4,0 + 5,2 + 5.6
    custos = {t: comissoes.infraestrutura.custo_tenant_mensal(dados, t)[0] for t in TENANTS}
    assert custos == {"t-ent": Decimal("400.00"), "t-biz": Decimal("520.00"), "t-corp": Decimal("560.00")}
    assert custos["t-biz"] == custos["t-ent"] * Decimal("1.3") and custos["t-corp"] == custos["t-ent"] * Decimal("1.4")


def test_migracao_publica_a_politica_com_os_pesos_novos_e_preserva_o_que_o_administrador_ajustou(monkeypatch):
    fd, caminho = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(caminho)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{caminho}")
    engine = sa.create_engine(f"sqlite:///{caminho}")
    try:
        config = Config("alembic.ini")
        command.upgrade(config, "b2d4f6a8c0e3")
        plano = sa.Table("plano", sa.MetaData(), autoload_with=engine)
        with engine.begin() as con:
            modelo = dict(con.execute(sa.select(plano).where(plano.c.nome == "Teste")).mappings().first())
            modelo.pop("id")
            con.execute(sa.insert(plano).values({**modelo, "nome": "Enterprise", "tier_infraestrutura": "ENTERPRISE", "visivel_self_service": True}))
        command.upgrade(config, "c3e5a7b9d1f4")  # cria Business e Corporate a partir do Enterprise (ainda com o tier dele)
        with engine.begin() as con:
            ativa = con.execute(sa.text("SELECT id, versao, regras FROM politica_comissao WHERE codigo = 'INFRASTRUCTURE_COST_POLICY' AND ativa = 1")).first()
            assert ativa is not None
            regras = json.loads(ativa[2])
            regras["pesos"]["ENTERPRISE"] = 5.0  # ajuste manual do administrador: a base do acréscimo é este peso
            con.execute(sa.text("UPDATE politica_comissao SET regras = :r WHERE id = :i"), {"r": json.dumps(regras), "i": ativa[0]})
        command.upgrade(config, "head")
        with engine.connect() as con:
            tiers = dict(con.execute(sa.text("SELECT nome, tier_infraestrutura FROM plano WHERE nome IN ('Business', 'Corporate')")).fetchall())
            assert tiers == {"Business": "BUSINESS", "Corporate": "CORPORATE"}
            linhas = con.execute(sa.text("SELECT versao, ativa, regras FROM politica_comissao WHERE codigo = 'INFRASTRUCTURE_COST_POLICY' ORDER BY versao")).fetchall()
            assert [(v, bool(a)) for v, a, _ in linhas] == [(1, False), (2, False), (3, True)]
            pesos = json.loads(linhas[-1][2])["pesos"]
            assert pesos["ENTERPRISE"] == 5.0 and pesos["BUSINESS"] == 6.5 and pesos["CORPORATE"] == 7.0  # 5,0 × 1,3 e 5,0 × 1,4
            assert pesos["STARTER"] == 1.0 and json.loads(linhas[-1][2])["custo_comissao"] == "PROVISIONED"
        command.upgrade(config, "head")  # idempotente: não publica outra versão
        with engine.connect() as con:
            assert con.execute(sa.text("SELECT COUNT(*) FROM politica_comissao WHERE codigo = 'INFRASTRUCTURE_COST_POLICY'")).scalar() == 3
        command.downgrade(config, "c3e5a7b9d1f4")
        with engine.connect() as con:
            assert con.execute(sa.text("SELECT COUNT(*) FROM politica_comissao WHERE codigo = 'INFRASTRUCTURE_COST_POLICY'")).scalar() == 2
            assert con.execute(sa.text("SELECT ativa FROM politica_comissao WHERE codigo = 'INFRASTRUCTURE_COST_POLICY' AND versao = 2")).scalar() == 1
            assert dict(con.execute(sa.text("SELECT nome, tier_infraestrutura FROM plano WHERE nome IN ('Business', 'Corporate')")).fetchall()) == {
                "Business": "ENTERPRISE", "Corporate": "ENTERPRISE"}
    finally:
        engine.dispose()
        if os.path.exists(caminho):
            os.remove(caminho)
