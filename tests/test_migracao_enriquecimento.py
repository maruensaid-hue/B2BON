"""Migração da governança de créditos de enriquecimento (a4c6e8b0d2f4): só tabelas novas, nenhum dado existente tocado, nenhum saldo inventado.
Únicos dados inseridos, todos informados pelo PO: o lote de compra, os pacotes adicionais e a franquia dos planos da matriz que existem no banco
(só o "Teste"; Starter/Professional não existem como planos avulsos, são "PREDATOR Starter" etc., e não são adivinhados). Downgrade devolve o banco
ao estado anterior sem perder o legado."""

import os
import tempfile
from decimal import Decimal

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

from app.core.config import settings

ANTERIOR = "f3d5a7c9e1b4"
TABELAS = ("enriquecimento_carteira", "enriquecimento_config_plano", "enriquecimento_orcamento_global", "enriquecimento_lote_compra",
           "enriquecimento_politica_provedor", "enriquecimento_uso_provedor", "pesquisa_decisores", "pesquisa_decisores_empresa",
           "pesquisa_decisores_transicao", "enriquecimento_movimento", "enriquecimento_pacote", "enriquecimento_compra")


def _banco(monkeypatch):
    fd, caminho = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(caminho)
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{caminho}")
    return caminho, sa.create_engine(f"sqlite:///{caminho}")


def test_migracao_preserva_o_legado_nao_inventa_configuracao_e_registra_so_o_lote_informado(monkeypatch):
    caminho, engine = _banco(monkeypatch)
    try:
        config = Config("alembic.ini")
        command.upgrade(config, ANTERIOR)
        with engine.begin() as conexao:
            conexao.execute(sa.text("INSERT INTO tenant (id, razao_social) VALUES ('t-mig', 'Migração')"))
            conexao.execute(sa.text("INSERT INTO conta (tenant_id, nome, status) VALUES ('t-mig', 'Empresa Legada', 'prospectada')"))
            conexao.execute(sa.text("INSERT INTO decisor (tenant_id, conta_id, nome, canal_provavel, origem) VALUES ('t-mig', 1, 'Decisor Legado', 'email', 'lusha')"))
            conexao.execute(sa.text("INSERT INTO carteira_creditos (tenant_id, saldo) VALUES ('t-mig', 50)"))
        antes = {t: _contagem(engine, t) for t in ("tenant", "conta", "decisor", "carteira_creditos", "lote_credito", "movimento_credito")}

        command.upgrade(config, "head")

        with engine.connect() as conexao:
            assert {t: _contagem(engine, t) for t in antes} == antes  # nada existente foi tocado, nem criado
            assert conexao.execute(sa.text("SELECT nome, origem FROM decisor")).fetchall() == [("Decisor Legado", "lusha")]
            for tabela in ("enriquecimento_politica_provedor", "enriquecimento_orcamento_global", "enriquecimento_movimento", "enriquecimento_carteira",
                           "enriquecimento_compra", "pesquisa_decisores"):
                assert _contagem(engine, tabela) == 0, tabela  # nenhum saldo, política, orçamento ou compra inventados: a Lusha segue bloqueada
            # Só o plano "Teste" da matriz existe no banco; os demais (POC, Starter, ...) não são criados nem adivinhados.
            configs = conexao.execute(sa.text(
                "SELECT p.nome, c.modo, c.franquia_creditos, c.periodicidade, c.limite_creditos_pesquisa, c.decisores_por_empresa_max, c.aprovado_por "
                "FROM enriquecimento_config_plano c JOIN plano p ON p.id = c.plano_id")).fetchall()
            assert configs == [("Teste", "franquia_fixa", 30, "mensal", 30, 3, "po:matriz-2026-10-21")]
            pacotes = conexao.execute(sa.text("SELECT codigo, quantidade_creditos, preco_unitario_brl, preco_total_brl, status FROM enriquecimento_pacote ORDER BY ordem")).fetchall()
            assert [(p[0], p[1], p[4]) for p in pacotes] == [("ENRIQ_400", 400, "ATIVO"), ("ENRIQ_660", 660, "ATIVO"), ("ENRIQ_1200", 1200, "ATIVO"),
                                                             ("ENRIQ_3000", 3000, "ATIVO"), ("ENRIQ_ACIMA_3000", None, "CONTACT_SALES")]
            assert [Decimal(str(p[3])) for p in pacotes[:4]] == [Decimal("540.00"), Decimal("844.80"), Decimal("1452.00"), Decimal("3240.00")]
            assert pacotes[4][2] is None and pacotes[4][3] is None  # acima de 3.000: sem preço, sem checkout
            lotes = conexao.execute(sa.text("SELECT provedor, referencia, quantidade_creditos, custo_total_brl, custo_unitario_brl FROM enriquecimento_lote_compra")).fetchall()
            assert len(lotes) == 1 and lotes[0][:3] == ("lusha", "APORTE-LUSHA-2026-10-21", 400)
            assert Decimal(str(lotes[0][3])) == Decimal("269.94") and Decimal(str(lotes[0][4])) == Decimal("0.67485")
    finally:
        engine.dispose()
        if os.path.exists(caminho):
            os.remove(caminho)


def test_downgrade_remove_so_as_tabelas_novas_e_o_upgrade_pode_ser_refeito(monkeypatch):
    caminho, engine = _banco(monkeypatch)
    try:
        config = Config("alembic.ini")
        command.upgrade(config, "head")
        with engine.begin() as conexao:
            conexao.execute(sa.text("INSERT INTO tenant (id, razao_social) VALUES ('t-mig', 'Migração')"))
            conexao.execute(sa.text("INSERT INTO conta (tenant_id, nome, status) VALUES ('t-mig', 'Empresa Legada', 'prospectada')"))
            conexao.execute(sa.text("INSERT INTO carteira_creditos (tenant_id, saldo) VALUES ('t-mig', 50)"))

        command.downgrade(config, ANTERIOR)

        with engine.connect() as conexao:
            existentes = {linha[0] for linha in conexao.execute(sa.text("SELECT name FROM sqlite_master WHERE type='table'"))}
            assert not (set(TABELAS) & existentes)  # as 12 tabelas saíram
            assert conexao.execute(sa.text("SELECT nome FROM conta")).fetchall() == [("Empresa Legada",)]  # legado e carteira de IA intactos
            assert float(conexao.execute(sa.text("SELECT saldo FROM carteira_creditos")).scalar()) == 50

        command.upgrade(config, "head")  # recuperação: sobe de novo sem erro
        assert _contagem(engine, "enriquecimento_lote_compra") == 1 and _contagem(engine, "enriquecimento_pacote") == 5
    finally:
        engine.dispose()
        if os.path.exists(caminho):
            os.remove(caminho)


def _contagem(engine, tabela: str) -> int:
    with engine.connect() as conexao:
        return conexao.execute(sa.text(f"SELECT count(*) FROM {tabela}")).scalar()
