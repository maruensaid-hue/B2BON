"""Planos da suíte: novos limites (planilha comercial de 2026-10-24) e os planos Business e Corporate.

Fonte: `Planos.xlsx` entregue pelo PO. Os limites vivem na tabela `plano` e são lidos pelo `NucleoPlanLimits` (franquia de contas, enriquecimento semanal,
cadências e campanhas por mês, usuários), então a aplicação passa a limitar os acessos por estes números sem outra mudança de lógica.

* Professional: enriquecimento de site e de contatos 200 -> 100 por semana.
* Enterprise: contas 5.000 -> 1.200; enriquecimento 1.250 -> 250; cadências 500 -> 150; campanhas 250 -> 100.
* Teste: enriquecimento de site 50 -> 30 e de contatos 50 -> 15.
* Business (R$ 6.485,00, 50 usuários) e Corporate (R$ 11.100,00, 100 usuários) são criados a partir do Enterprise (módulos, tier de infraestrutura, recursos), só
  se ainda não existirem, já com a franquia de pesquisa de decisores da matriz (120/120/20 e 180/180/30).

Cada coluna só é alterada se ainda tem o valor anterior (uma mudança feita por um administrador depois não é sobrescrita). Plano que não existe no banco é pulado.

Downgrade: devolve os valores anteriores onde estão iguais aos novos e remove Business/Corporate se ainda não têm licença.

Revision ID: c3e5a7b9d1f4
Revises: b2d4f6a8c0e3
Create Date: 2026-10-24
"""
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

from app.contexts.enriquecimento.matriz_dados import APROVADOR_MATRIZ, MOTIVO_MATRIZ, PLANOS

revision = "c3e5a7b9d1f4"
down_revision = "b2d4f6a8c0e3"
branch_labels = None
depends_on = None

# (plano, coluna, valor anterior, valor novo)
_AJUSTES = (
    ("Professional", "limite_enriquecimento_site_semanal", 200, 100),
    ("Professional", "limite_enriquecimento_contatos_semanal", 200, 100),
    ("Enterprise", "franquia_contas_mes", 5000, 1200),
    ("Enterprise", "limite_enriquecimento_site_semanal", 1250, 250),
    ("Enterprise", "limite_enriquecimento_contatos_semanal", 1250, 250),
    ("Enterprise", "limite_cadencias_mes", 500, 150),
    ("Enterprise", "limite_campanhas_mes", 250, 100),
    ("Teste", "limite_enriquecimento_site_semanal", 50, 30),
    ("Teste", "limite_enriquecimento_contatos_semanal", 50, 15),
)
_NOVOS = (
    {"nome": "Business", "preco_mensal": 6485.00, "max_usuarios": 50, "franquia_contas_mes": 2500, "limite_enriquecimento_site_semanal": 500,
     "limite_enriquecimento_contatos_semanal": 500, "limite_cadencias_mes": 300, "limite_campanhas_mes": 200},
    {"nome": "Corporate", "preco_mensal": 11100.00, "max_usuarios": 100, "franquia_contas_mes": 5000, "limite_enriquecimento_site_semanal": 1000,
     "limite_enriquecimento_contatos_semanal": 1000, "limite_cadencias_mes": 500, "limite_campanhas_mes": 400},
)


def upgrade() -> None:
    """Ajusta os limites dos planos existentes (só onde ainda valem os valores antigos) e cria Business e Corporate a partir do Enterprise, se ainda não existirem."""
    conexao = op.get_bind()
    plano = sa.Table("plano", sa.MetaData(), autoload_with=conexao)
    for nome, coluna, antigo, novo in _AJUSTES:
        conexao.execute(sa.update(plano).where(plano.c.nome == nome, plano.c[coluna] == antigo).values({coluna: novo}))

    base = conexao.execute(sa.select(plano).where(plano.c.nome == "Enterprise")).mappings().first()
    if base is None:  # banco sem a suíte (a criação inicial de planos já traz os valores novos)
        return
    agora = datetime.now(timezone.utc).replace(tzinfo=None)
    configs = sa.table(
        "enriquecimento_config_plano",
        sa.column("plano_id", sa.Integer), sa.column("versao", sa.Integer), sa.column("modo", sa.String), sa.column("franquia_creditos", sa.Integer),
        sa.column("periodicidade", sa.String), sa.column("decisores_por_empresa_max", sa.Integer), sa.column("limite_creditos_pesquisa", sa.Integer),
        sa.column("motivo", sa.String), sa.column("criado_por", sa.String), sa.column("aprovado_por", sa.String), sa.column("aprovado_em", sa.DateTime),
        sa.column("valido_de", sa.DateTime),
    )
    for dados in _NOVOS:
        if conexao.execute(sa.select(plano.c.id).where(plano.c.nome == dados["nome"])).first() is not None:
            continue
        linha = {c: v for c, v in base.items() if c != "id"}
        linha.update(dados, recomendado=False, visivel_self_service=True)
        novo_id = conexao.execute(sa.insert(plano).values(linha)).inserted_primary_key[0]
        spec = PLANOS[dados["nome"]]["config"]  # franquia de pesquisa de decisores da matriz (Business 120/120/20, Corporate 180/180/30)
        conexao.execute(sa.insert(configs).values(
            plano_id=novo_id, versao=1, modo=spec["modo"], franquia_creditos=spec["franquia_creditos"], periodicidade=spec["periodicidade"],
            decisores_por_empresa_max=spec["decisores_por_empresa_max"], limite_creditos_pesquisa=spec["limite_creditos_pesquisa"], motivo=MOTIVO_MATRIZ,
            criado_por="migracao", aprovado_por=APROVADOR_MATRIZ, aprovado_em=agora, valido_de=agora,
        ))


def downgrade() -> None:
    """Devolve os limites antigos onde estão iguais aos novos e remove Business/Corporate que ainda não têm licença."""
    conexao = op.get_bind()
    plano = sa.Table("plano", sa.MetaData(), autoload_with=conexao)
    for nome, coluna, antigo, novo in _AJUSTES:
        conexao.execute(sa.update(plano).where(plano.c.nome == nome, plano.c[coluna] == novo).values({coluna: antigo}))
    licenca = sa.table("licenca", sa.column("plano_id", sa.Integer))
    configs = sa.table("enriquecimento_config_plano", sa.column("plano_id", sa.Integer))
    for dados in _NOVOS:
        linha = conexao.execute(sa.select(plano.c.id).where(plano.c.nome == dados["nome"])).first()
        if linha is None:
            continue
        if conexao.execute(sa.select(licenca.c.plano_id).where(licenca.c.plano_id == linha[0])).first() is None:
            conexao.execute(sa.delete(configs).where(configs.c.plano_id == linha[0]))
            conexao.execute(sa.delete(plano).where(plano.c.id == linha[0]))
