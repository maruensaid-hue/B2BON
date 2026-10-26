"""Planos da suíte (planilha comercial de 2026-10-24): cada plano limita o acesso pelos números da planilha. Os limites vivem na tabela `plano` e são lidos pelo
`NucleoPlanLimitsProvider`; aqui conferimos os valores do seed, a leitura pelo provedor, a aplicação dos bloqueios e a migração que atualiza a produção."""

import importlib
import logging
import os
import tempfile
import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from app.core.config import settings
from app.models.cadencia import Cadencia
from app.models.licenca import Licenca
from app.models.plano import Plano
from app.models.tenant import Tenant
from app.providers.plan_limits.nucleo import NucleoPlanLimitsProvider
from app.services import limite_criacao_service
from app.services.errors import RegraNegocioViolada


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


# nome: (mensalidade, usuários, contas/mês, enriquecimento site/semana, enriquecimento contatos/semana, cadências/mês, campanhas/mês)
PLANILHA = {
    "POC": (0.0, 3, 50, 15, 15, 5, 2),
    "Starter": (924.5, 5, 200, 50, 50, 20, 10),
    "Professional": (1664.1, 10, 800, 100, 100, 80, 40),
    "Enterprise": (2958.4, 20, 1200, 250, 250, 150, 100),
    "Business": (6485.0, 50, 2500, 500, 500, 300, 200),
    "Corporate": (11100.0, 100, 5000, 1000, 1000, 500, 400),
    "Teste": (0.0, None, 200, 30, 15, 20, 10),
}


def _seed() -> dict[str, dict]:
    bootstrap = importlib.import_module("scripts.bootstrap_tenant")
    return {p["nome"]: p for p in bootstrap.PLANOS_PADRAO}


def _tupla(d) -> tuple:
    return (d["preco_mensal"], d["max_usuarios"], d["franquia_contas_mes"], d["limite_enriquecimento_site_semanal"], d["limite_enriquecimento_contatos_semanal"],
            d["limite_cadencias_mes"], d["limite_campanhas_mes"])


@pytest.mark.parametrize("nome", list(PLANILHA))
def test_seed_dos_planos_segue_a_planilha(nome):
    assert _tupla(_seed()[nome]) == PLANILHA[nome]


@pytest.mark.parametrize("nome", ["Business", "Corporate"])
def test_planos_novos_liberam_os_tres_modulos_e_aparecem_no_autoatendimento(nome):
    seed = _seed()[nome]
    assert seed["modulos_contratados"] == ["map", "predator", "crm"] and seed["categoria"] == "suite" and seed.get("visivel_self_service", True) is True


def _licenciar(db, nome: str, tenant_id: str) -> None:
    plano = Plano(**{k: v for k, v in _seed()[nome].items()})
    db.add(plano)
    db.add(Tenant(id=tenant_id, razao_social=f"Cliente {nome}"))
    db.flush()
    db.add(Licenca(tenant_id=tenant_id, plano_id=plano.id, status="ativa"))
    db.commit()


@pytest.mark.parametrize("nome", list(PLANILHA))
def test_provedor_de_limites_devolve_os_numeros_do_plano_contratado(db_session, nome):
    tenant = f"t-{nome.lower()}"
    _licenciar(db_session, nome, tenant)
    limites = NucleoPlanLimitsProvider(db_session)
    _, usuarios, contas, site, contatos, cadencias, campanhas = PLANILHA[nome]
    assert (limites.obter_limite_usuarios(tenant), limites.obter_franquia_contas_mes(tenant), limites.obter_limite_enriquecimento_site_semanal(tenant),
            limites.obter_limite_enriquecimento_contatos_semanal(tenant), limites.obter_limite_cadencias_mes(tenant),
            limites.obter_limite_campanhas_mes(tenant)) == (usuarios, contas, site, contatos, cadencias, campanhas)


def test_limite_de_cadencias_do_plano_bloqueia_a_criacao_acima_do_contratado(db_session):
    _licenciar(db_session, "POC", "t-poc-limite")  # POC: 5 cadências por mês
    limites = NucleoPlanLimitsProvider(db_session)
    for i in range(5):
        limite_criacao_service.verificar_limite_cadencias(db_session, "t-poc-limite", limites)
        db_session.add(Cadencia(tenant_id="t-poc-limite", nome=f"c{i}", canais=["email", "whatsapp"], status="rascunho", tipo="prospeccao"))
        db_session.commit()
    with pytest.raises(RegraNegocioViolada, match="Limite de cadências do seu plano"):
        limite_criacao_service.verificar_limite_cadencias(db_session, "t-poc-limite", limites)


def test_plano_maior_libera_mais_que_o_menor(db_session):
    _licenciar(db_session, "Starter", "t-start")
    _licenciar(db_session, "Business", "t-biz")
    limites = NucleoPlanLimitsProvider(db_session)
    assert limites.obter_limite_cadencias_mes("t-biz") > limites.obter_limite_cadencias_mes("t-start")
    assert limites.obter_limite_usuarios("t-biz") == 50 and limites.obter_limite_usuarios("t-start") == 5


def test_migracao_aplica_os_novos_limites_cria_business_e_corporate_e_preserva_ajuste_manual(monkeypatch):
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
            for nome, extras in (
                ("Professional", dict(preco_mensal=1664.1, max_usuarios=10, franquia_contas_mes=800, limite_enriquecimento_site_semanal=200,
                                      limite_enriquecimento_contatos_semanal=200, limite_cadencias_mes=80, limite_campanhas_mes=40, visivel_self_service=True)),
                ("Enterprise", dict(preco_mensal=2958.4, max_usuarios=20, franquia_contas_mes=5000, limite_enriquecimento_site_semanal=1250,
                                    limite_enriquecimento_contatos_semanal=1250, limite_cadencias_mes=500, limite_campanhas_mes=250, visivel_self_service=True,
                                    tier_infraestrutura="ENTERPRISE")),
            ):
                con.execute(sa.insert(plano).values({**modelo, "nome": nome, **extras}))
            # um administrador já tinha ajustado as cadências do Enterprise: esse valor não pode ser sobrescrito
            con.execute(sa.update(plano).where(plano.c.nome == "Enterprise").values(limite_cadencias_mes=777))
        command.upgrade(config, "head")
        with engine.connect() as con:
            linhas = {r["nome"]: r for r in con.execute(sa.select(plano)).mappings()}
            tupla = lambda r: (float(r["preco_mensal"]), r["max_usuarios"], r["franquia_contas_mes"], r["limite_enriquecimento_site_semanal"],  # noqa: E731
                               r["limite_enriquecimento_contatos_semanal"], r["limite_cadencias_mes"], r["limite_campanhas_mes"])
            assert tupla(linhas["Professional"]) == PLANILHA["Professional"]
            enterprise = list(PLANILHA["Enterprise"])
            enterprise[5] = 777
            assert tupla(linhas["Enterprise"]) == tuple(enterprise)
            assert (linhas["Teste"]["limite_enriquecimento_site_semanal"], linhas["Teste"]["limite_enriquecimento_contatos_semanal"]) == (30, 15)
            for nome in ("Business", "Corporate"):
                assert tupla(linhas[nome]) == PLANILHA[nome] and linhas[nome]["tier_infraestrutura"] == nome.upper() and linhas[nome]["categoria"] == "suite"
                assert linhas[nome]["modulos_contratados"] in (["map", "predator", "crm"], '["map", "predator", "crm"]')
            configs = con.execute(sa.text(
                "SELECT p.nome, c.franquia_creditos, c.limite_creditos_pesquisa, c.decisores_por_empresa_max FROM enriquecimento_config_plano c "
                "JOIN plano p ON p.id = c.plano_id WHERE p.nome IN ('Business', 'Corporate') ORDER BY p.nome")).fetchall()
            assert configs == [("Business", 120, 120, 20), ("Corporate", 180, 180, 30)]
        command.upgrade(config, "head")  # idempotente
        with engine.connect() as con:
            assert con.execute(sa.text("SELECT COUNT(*) FROM plano WHERE nome IN ('Business', 'Corporate')")).scalar() == 2
        command.downgrade(config, "b2d4f6a8c0e3")
        with engine.connect() as con:
            assert con.execute(sa.text("SELECT COUNT(*) FROM plano WHERE nome IN ('Business', 'Corporate')")).scalar() == 0
            assert con.execute(sa.text("SELECT limite_enriquecimento_site_semanal FROM plano WHERE nome = 'Enterprise'")).scalar() == 1250
    finally:
        engine.dispose()
        if os.path.exists(caminho):
            os.remove(caminho)


def test_seed_liga_business_e_corporate_aos_tiers_de_infraestrutura_proprios():
    seed = _seed()
    assert (seed["Business"]["tier_infraestrutura"], seed["Corporate"]["tier_infraestrutura"]) == ("BUSINESS", "CORPORATE")
