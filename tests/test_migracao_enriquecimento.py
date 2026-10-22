"""Migração da governança de créditos de enriquecimento (a4c6e8b0d2f4): só tabelas novas, nenhum dado existente tocado, nenhum saldo inventado.
Únicos dados inseridos, todos informados pelo PO: o lote de compra, os pacotes adicionais e a franquia dos planos da matriz que existem no banco
(só o "Teste"; Starter/Professional não existem como planos avulsos, são "PREDATOR Starter" etc., e não são adivinhados), mais a base econômica do provedor de contatos
(USD 600/mês, 81.600 créditos/ano, câmbio de planejamento R$ 6,00) e o orçamento global de 6.800 créditos/mês. A compra pontual de
R$ 269,94 por 400 créditos é removida. Downgrade devolve o banco ao estado anterior sem perder o legado."""

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
           "pesquisa_decisores_transicao", "enriquecimento_movimento", "enriquecimento_pacote", "enriquecimento_compra", "enriquecimento_custo_provedor",
           "enriquecimento_pagamento_provedor", "enriquecimento_nota_fiscal", "enriquecimento_estorno_compra")


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
            conexao.execute(sa.text("INSERT INTO decisor (tenant_id, conta_id, nome, canal_provavel, origem) VALUES ('t-mig', 1, 'Decisor Legado', 'email', 'contatos')"))
            conexao.execute(sa.text("INSERT INTO carteira_creditos (tenant_id, saldo) VALUES ('t-mig', 50)"))
        antes = {t: _contagem(engine, t) for t in ("tenant", "conta", "decisor", "carteira_creditos", "lote_credito", "movimento_credito")}

        command.upgrade(config, "head")

        with engine.connect() as conexao:
            assert {t: _contagem(engine, t) for t in antes} == antes  # nada existente foi tocado, nem criado
            assert conexao.execute(sa.text("SELECT nome, origem FROM decisor")).fetchall() == [("Decisor Legado", "contatos")]
            for tabela in ("enriquecimento_politica_provedor", "enriquecimento_movimento", "enriquecimento_carteira", "enriquecimento_compra",
                           "enriquecimento_pagamento_provedor", "enriquecimento_nota_fiscal", "enriquecimento_estorno_compra", "pesquisa_decisores"):
                assert _contagem(engine, tabela) == 0, tabela  # nenhum saldo, política, orçamento ou compra inventados: o provedor de contatos segue bloqueada
            # Existem no banco o "Teste" e os planos de módulo PREDATOR Starter/Professional (mesma franquia de pesquisa de decisores); POC, Business,
            # Corporate e os planos da suíte que não existem aqui não são criados.
            configs = conexao.execute(sa.text(
                "SELECT p.nome, c.modo, c.franquia_creditos, c.periodicidade, c.limite_creditos_pesquisa, c.decisores_por_empresa_max, c.aprovado_por "
                "FROM enriquecimento_config_plano c JOIN plano p ON p.id = c.plano_id ORDER BY p.nome")).fetchall()
            assert configs == [("PREDATOR Professional", "franquia_fixa", 60, "mensal", 60, 10, "po:matriz-2026-10-21"),
                               ("PREDATOR Starter", "franquia_fixa", 30, "mensal", 30, 5, "po:matriz-2026-10-21"),
                               ("Teste", "franquia_fixa", 30, "mensal", 30, 3, "po:matriz-2026-10-21")]
            pacotes = conexao.execute(sa.text("SELECT codigo, quantidade_creditos, preco_unitario_brl, preco_total_brl, status FROM enriquecimento_pacote ORDER BY ordem")).fetchall()
            assert [(p[0], p[1], p[4]) for p in pacotes] == [("ENRIQ_400", 400, "ATIVO"), ("ENRIQ_660", 660, "ATIVO"), ("ENRIQ_1200", 1200, "ATIVO"),
                                                             ("ENRIQ_3000", 3000, "ATIVO"), ("ENRIQ_ACIMA_3000", None, "CONTACT_SALES")]
            assert [Decimal(str(p[3])) for p in pacotes[:4]] == [Decimal("540.00"), Decimal("844.80"), Decimal("1452.00"), Decimal("3240.00")]
            assert pacotes[4][2] is None and pacotes[4][3] is None  # acima de 3.000: sem preço, sem checkout
            # A compra pontual de 400 créditos por R$ 269,94 foi desconsiderada pelo PO: semeada pela migração anterior e removida pela seguinte.
            assert _contagem(engine, "enriquecimento_lote_compra") == 0
            custo = conexao.execute(sa.text("SELECT provedor, versao, custo_mensal_usd, creditos_anuais, creditos_mensais, cambio_planejamento_brl, custo_unitario_usd, "
                                            "custo_unitario_brl, custo_mensal_brl, aprovado_por FROM enriquecimento_custo_provedor")).fetchall()
            assert len(custo) == 1 and custo[0][:2] == ("contatos", 1) and custo[0][3:5] == (81600, 6800) and custo[0][9] == "po:custo-contatos-2026-10-21"
            assert Decimal(str(custo[0][2])) == Decimal(600) and Decimal(str(custo[0][5])) == Decimal(6) and Decimal(str(custo[0][8])) == Decimal(3600)
            assert Decimal(str(custo[0][6])).quantize(Decimal("0.000000001")) == Decimal("0.088235294")
            assert Decimal(str(custo[0][7])).quantize(Decimal("0.000000001")) == Decimal("0.529411765")
            colunas = {c["name"] for c in sa.inspect(engine).get_columns("enriquecimento_custo_provedor")}
            assert not {"contrato_validado_em", "contrato_checklist", "saldo_transferivel"} & colunas  # não há etapa de validação de contrato
            orcamento = conexao.execute(sa.text("SELECT provedor, versao, limite_creditos, alerta_percentual, aprovado_por FROM enriquecimento_orcamento_global")).fetchall()
            assert orcamento == [("contatos", 1, 6800, 80, "po:custo-contatos-2026-10-21")]  # capacidade equivalente ao teto de USD 600
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
            assert not (set(TABELAS) & existentes)  # as 16 tabelas saíram
            assert conexao.execute(sa.text("SELECT nome FROM conta")).fetchall() == [("Empresa Legada",)]  # legado e carteira de IA intactos
            assert float(conexao.execute(sa.text("SELECT saldo FROM carteira_creditos")).scalar()) == 50

        command.upgrade(config, "head")  # recuperação: sobe de novo sem erro
        assert _contagem(engine, "enriquecimento_lote_compra") == 0 and _contagem(engine, "enriquecimento_pacote") == 5 and _contagem(engine, "enriquecimento_custo_provedor") == 1
    finally:
        engine.dispose()
        if os.path.exists(caminho):
            os.remove(caminho)


def test_lote_desconsiderado_so_e_removido_quando_nenhuma_politica_o_referencia(monkeypatch):
    caminho, engine = _banco(monkeypatch)
    try:
        config = Config("alembic.ini")
        command.upgrade(config, "a4c6e8b0d2f4")  # estado do staging antes desta mudança: o lote de R$ 269,94 / 400 está semeado
        with engine.begin() as conexao:
            lote_id = conexao.execute(sa.text("SELECT id FROM enriquecimento_lote_compra")).scalar()
            conexao.execute(sa.text("INSERT INTO enriquecimento_politica_provedor (provedor, versao, revelar_emails, revelar_telefones, casas_exibicao, lote_compra_id, "
                                    "custo_unitario_brl) VALUES ('contatos', 1, 0, 0, 2, :l, 0.67485)"), {"l": lote_id})
        command.upgrade(config, "head")
        with engine.connect() as conexao:
            assert _contagem(engine, "enriquecimento_lote_compra") == 1  # referenciado por uma política: preservado (o histórico não é apagado)
            assert float(conexao.execute(sa.text("SELECT custo_unitario_brl FROM enriquecimento_politica_provedor")).scalar()) == 0.67485
            assert _contagem(engine, "enriquecimento_custo_provedor") == 1
    finally:
        engine.dispose()
        if os.path.exists(caminho):
            os.remove(caminho)


def _contagem(engine, tabela: str) -> int:
    with engine.connect() as conexao:
        return conexao.execute(sa.text(f"SELECT count(*) FROM {tabela}")).scalar()


def test_migracao_que_libera_os_planos_da_matriz_nao_sobrescreve_configuracao_ja_definida(monkeypatch):
    """e8a0c2d4f6b8: aplica a matriz aos planos PREDATOR que ainda não têm configuração; o que um administrador já definiu fica como está."""
    caminho, engine = _banco(monkeypatch)
    try:
        config = Config("alembic.ini")
        command.upgrade(config, "d7f9b1c3e5a7")
        with engine.begin() as conexao:
            ids = {nome: i for i, nome in conexao.execute(sa.text("SELECT id, nome FROM plano")).fetchall()}
            conexao.execute(sa.text("DELETE FROM enriquecimento_config_plano WHERE plano_id IN (:a, :b)"), {"a": ids["PREDATOR Starter"], "b": ids["PREDATOR Professional"]})
            conexao.execute(sa.text(
                "INSERT INTO enriquecimento_config_plano (plano_id, versao, modo, franquia_creditos, periodicidade, limite_creditos_pesquisa, decisores_por_empresa_max, "
                "motivo, criado_por, aprovado_por, aprovado_em, valido_de) VALUES (:p, 1, 'franquia_fixa', 999, 'mensal', 999, 7, 'admin', 'admin', 'admin', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"), {"p": ids["PREDATOR Professional"]})
        command.upgrade(config, "head")
        with engine.connect() as conexao:
            linhas = conexao.execute(sa.text(
                "SELECT p.nome, c.franquia_creditos, c.limite_creditos_pesquisa, c.decisores_por_empresa_max FROM enriquecimento_config_plano c "
                "JOIN plano p ON p.id = c.plano_id WHERE p.nome LIKE 'PREDATOR%' ORDER BY p.nome")).fetchall()
        assert linhas == [("PREDATOR Professional", 999, 999, 7), ("PREDATOR Starter", 30, 30, 5)]  # Starter liberado; Professional do admin preservado
        command.downgrade(config, "d7f9b1c3e5a7")
        with engine.connect() as conexao:
            assert conexao.execute(sa.text("SELECT COUNT(*) FROM enriquecimento_config_plano c JOIN plano p ON p.id = c.plano_id WHERE p.nome = 'PREDATOR Starter'")).scalar() == 0
    finally:
        engine.dispose()
        if os.path.exists(caminho):
            os.remove(caminho)


def test_migracao_da_poc_limita_a_3_pesquisas_so_na_linha_ainda_sem_limite(monkeypatch):
    """f9b1d3e5a7c9: a linha POC aprovada pelo PO (1 decisor) ganha o limite de 3 pesquisas; o downgrade devolve o estado anterior."""
    caminho, engine = _banco(monkeypatch)
    try:
        config = Config("alembic.ini")
        command.upgrade(config, "e8a0c2d4f6b8")
        consulta = sa.text("SELECT c.limite_pesquisas_periodo FROM enriquecimento_config_plano c JOIN plano p ON p.id = c.plano_id WHERE p.nome = 'PREDATOR Starter'")
        with engine.begin() as conexao:  # no banco real a linha POC é de um plano criado fora das migrações; aqui um plano de módulo faz o papel dela
            conexao.execute(sa.text("UPDATE enriquecimento_config_plano SET modo = 'poc_autorizada' WHERE plano_id = (SELECT id FROM plano WHERE nome = 'PREDATOR Starter')"))
        with engine.connect() as conexao:
            antes = conexao.execute(consulta).fetchall()
        command.upgrade(config, "head")
        with engine.connect() as conexao:
            depois = conexao.execute(consulta).fetchall()
        command.downgrade(config, "e8a0c2d4f6b8")
        with engine.connect() as conexao:
            revertido = conexao.execute(consulta).fetchall()
        assert (antes, depois, revertido) == ([(None,)], [(3,)], [(None,)])
    finally:
        engine.dispose()
        if os.path.exists(caminho):
            os.remove(caminho)


def test_migracao_que_remove_o_nome_do_fornecedor_acerta_os_dados_ja_gravados(monkeypatch):
    """a1c3e5b7d9f1: valores de identificação e textos que citavam o fornecedor passam a ser neutros; o resto não é tocado."""
    antigo = "ahsul"[::-1]  # o nome do fornecedor não é escrito por extenso nos testes
    caminho, engine = _banco(monkeypatch)
    try:
        config = Config("alembic.ini")
        command.upgrade(config, "f9b1d3e5a7c9")
        with engine.begin() as conexao:
            conexao.execute(sa.text("INSERT INTO tenant (id, razao_social) VALUES ('t-nome', 'Nome')"))
            conexao.execute(sa.text("INSERT INTO conta (tenant_id, nome, status) VALUES ('t-nome', 'Empresa', 'prospectada')"))
            conexao.execute(sa.text(f"INSERT INTO decisor (tenant_id, conta_id, nome, canal_provavel, origem) VALUES ('t-nome', 1, 'Pessoa', 'email', '{antigo}')"))
            conexao.execute(sa.text("INSERT INTO decisor (tenant_id, conta_id, nome, canal_provavel, origem) VALUES ('t-nome', 1, 'Outra', 'email', 'qsa')"))
            conexao.execute(sa.text("UPDATE enriquecimento_custo_provedor SET provedor = :p, aprovado_por = :a, motivo = :m"),
                            {"p": antigo, "a": f"po:custo-{antigo}-2026-10-21", "m": f"Base econômica {antigo.title()} informada pelo PO"})
            conexao.execute(sa.text("UPDATE enriquecimento_orcamento_global SET provedor = :p"), {"p": antigo})
            conexao.execute(sa.text("INSERT INTO atividade (tenant_id, conta_id, tipo, descricao) VALUES ('t-nome', 1, 'sistema', 'IA enriqueceu via BrasilAPI')"))
            conexao.execute(sa.text("INSERT INTO campo_enriquecido (conta_id, campo, valor, fonte, coletado_em) VALUES (1, 'porte', 'ME', 'brasilapi_cnpj', CURRENT_TIMESTAMP)"))
        command.upgrade(config, "head")
        with engine.connect() as conexao:
            assert sorted(r[0] for r in conexao.execute(sa.text("SELECT origem FROM decisor")).fetchall()) == ["contatos", "qsa"]
            custo = conexao.execute(sa.text("SELECT provedor, aprovado_por, motivo FROM enriquecimento_custo_provedor")).fetchall()
            assert custo == [("contatos", "po:custo-contatos-2026-10-21", "Base econômica provedor de contatos informada pelo PO")]
            assert conexao.execute(sa.text("SELECT provedor FROM enriquecimento_orcamento_global")).fetchall() == [("contatos",)]
            assert conexao.execute(sa.text("SELECT descricao FROM atividade")).fetchall() == [("IA enriqueceu com dados cadastrais públicos",)]
            assert conexao.execute(sa.text("SELECT fonte FROM campo_enriquecido")).fetchall() == [("cadastro_publico_cnpj",)]
            for tabela, coluna in (("enriquecimento_politica_provedor", "motivo"), ("enriquecimento_pacote", "motivo"), ("enriquecimento_config_plano", "motivo")):
                assert conexao.execute(sa.text(f"SELECT COUNT(*) FROM {tabela} WHERE lower({coluna}) LIKE :n"), {"n": f"%{antigo}%"}).scalar() == 0
    finally:
        engine.dispose()
        if os.path.exists(caminho):
            os.remove(caminho)
