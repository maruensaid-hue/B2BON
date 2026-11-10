"""Migração dos planos de 1 usuário (b6d8f0a2c4e7): criados a partir do Starter equivalente, com 1 usuário, preço e limites do PO."""

import os
import tempfile

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from app.core.config import settings

ANTERIOR = "a4c6e8f0b2d3"


def test_cria_os_quatro_planos_individuais_e_o_downgrade_remove(monkeypatch):
    fd, caminho = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(caminho)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{caminho}")
    engine = sa.create_engine(f"sqlite:///{caminho}")
    try:
        config = Config("alembic.ini")
        command.upgrade(config, ANTERIOR)
        with engine.begin() as conexao:
            # Num banco montado só pelas migrações o "Starter" da suíte não existe (nasce na carga inicial); em produção existe.
            if conexao.execute(sa.text("SELECT COUNT(*) FROM plano WHERE nome = 'Starter'")).scalar() == 0:
                colunas = [c for (c,) in [(r[1],) for r in conexao.execute(sa.text("PRAGMA table_info(plano)"))] if c not in ("id", "nome")]
                lista = ", ".join(colunas)
                conexao.execute(sa.text(f"INSERT INTO plano (nome, {lista}) SELECT 'Starter', {lista} FROM plano WHERE nome = 'PREDATOR Starter'"))
                conexao.execute(sa.text("UPDATE plano SET modulos_contratados = '[\"map\", \"predator\", \"crm\"]', categoria = 'suite', "
                                        "preco_mensal = 924.5, franquia_contas_mes = 200, limite_cadencias_mes = 20 WHERE nome = 'Starter'"))
        with engine.connect() as conexao:
            bases = {n for (n,) in conexao.execute(sa.text(
                "SELECT nome FROM plano WHERE nome IN ('Starter','PREDATOR Starter','CRM Starter','MAP Starter')"))}

        command.upgrade(config, "head")

        with engine.connect() as conexao:
            linhas = {
                nome: (preco, usuarios, contas, cadencias, modulos)
                for nome, preco, usuarios, contas, cadencias, modulos in conexao.execute(sa.text(
                    "SELECT nome, preco_mensal, max_usuarios, franquia_contas_mes, limite_cadencias_mes, modulos_contratados FROM plano "
                    "WHERE nome LIKE '%Individual'"))
            }
            config_suite = conexao.execute(sa.text(
                "SELECT c.franquia_creditos FROM enriquecimento_config_plano c JOIN plano p ON p.id = c.plano_id WHERE p.nome = 'Individual'"
            )).scalar()
        esperados = {"Individual": "Starter", "PREDATOR Individual": "PREDATOR Starter", "CRM Individual": "CRM Starter",
                     "MAP Individual": "MAP Starter"}
        assert set(linhas) == {novo for novo, base in esperados.items() if base in bases}
        if "Individual" in linhas:
            preco, usuarios, contas, cadencias, modulos = linhas["Individual"]
            assert (preco, usuarios, contas, cadencias) == (149.90, 1, 40, 4)
            assert set(modulos if isinstance(modulos, list) else __import__("json").loads(modulos)) == {"map", "predator", "crm"}
            assert config_suite in (None, 6)
        if "MAP Individual" in linhas:
            assert linhas["MAP Individual"][:3] == (29.90, 1, 0)

        command.downgrade(config, ANTERIOR)
        with engine.connect() as conexao:
            assert conexao.execute(sa.text("SELECT COUNT(*) FROM plano WHERE nome LIKE '%Individual'")).scalar() == 0
    finally:
        engine.dispose()
        os.remove(caminho)
