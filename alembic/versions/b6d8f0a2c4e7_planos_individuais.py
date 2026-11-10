"""Planos de 1 usuário (assinatura individual): suíte e cada módulo, com checkout self-service.

Decisão do PO em 2026-11-10: a tabela pública mostrava preço por usuário, mas o menor plano assinável era de 5 usuários. Cada plano
individual é criado a partir do Starter equivalente (módulos liberados, recursos, tier de infraestrutura), com 1 usuário e limites
proporcionais (Starter ÷ 5):

* Individual (suíte): R$ 149,90, 40 contas/mês, enriquecimento 10/10 por semana, 4 cadências e 2 campanhas por mês.
* PREDATOR Individual: R$ 95,10, 40 contas/mês, mesmos limites de prospecção.
* CRM Individual: R$ 59,90 e MAP Individual: R$ 29,90 — sem franquia de contas, igual aos Starter desses módulos (não geram listas).

A franquia de pesquisa de decisores (`enriquecimento_config_plano`) segue a do Starter ÷ 5 (6 créditos/mês), só onde o Starter tem uma.
Cada plano só é criado se ainda não existir; o downgrade remove os que ainda não têm licença.

Revision ID: b6d8f0a2c4e7
Revises: a4c6e8f0b2d3
Create Date: 2026-11-10
"""
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "b6d8f0a2c4e7"
down_revision = "a4c6e8f0b2d3"
branch_labels = None
depends_on = None

_LIMITES_PROSPECCAO = {
    "franquia_contas_mes": 40, "limite_enriquecimento_site_semanal": 10, "limite_enriquecimento_contatos_semanal": 10,
    "limite_cadencias_mes": 4, "limite_campanhas_mes": 2,
}
# (novo plano, plano base, preço, limites próprios)
_NOVOS = (
    ("Individual", "Starter", 149.90, _LIMITES_PROSPECCAO),
    ("PREDATOR Individual", "PREDATOR Starter", 95.10, _LIMITES_PROSPECCAO),
    ("CRM Individual", "CRM Starter", 59.90, {}),
    ("MAP Individual", "MAP Starter", 29.90, {}),
)
_DIVISOR_INDIVIDUAL = 5  # o Starter é de 5 usuários
_MOTIVO = "Plano de 1 usuário (assinatura individual) aprovado pelo PO em 2026-11-10: franquia do Starter dividida por 5"


def upgrade() -> None:
    conexao = op.get_bind()
    plano = sa.Table("plano", sa.MetaData(), autoload_with=conexao)
    configs = sa.Table("enriquecimento_config_plano", sa.MetaData(), autoload_with=conexao)
    agora = datetime.now(timezone.utc).replace(tzinfo=None)
    for nome, nome_base, preco, limites in _NOVOS:
        if conexao.execute(sa.select(plano.c.id).where(plano.c.nome == nome)).first() is not None:
            continue
        base = conexao.execute(sa.select(plano).where(plano.c.nome == nome_base)).mappings().first()
        if base is None:  # banco sem o Starter equivalente (ex.: banco de teste vazio)
            continue
        linha = {c: v for c, v in base.items() if c != "id"}
        linha.update(limites, nome=nome, preco_mensal=preco, max_usuarios=1, recomendado=False, visivel_self_service=True)
        novo_id = conexao.execute(sa.insert(plano).values(linha)).inserted_primary_key[0]

        config_base = conexao.execute(
            sa.select(configs).where(configs.c.plano_id == base["id"], configs.c.tenant_id.is_(None)).order_by(configs.c.versao.desc())
        ).mappings().first()
        if config_base is None:
            continue
        copia = {c: v for c, v in config_base.items() if c not in ("id", "criado_em")}
        for coluna in ("franquia_creditos", "limite_creditos_pesquisa"):
            if copia.get(coluna):
                copia[coluna] = max(1, copia[coluna] // _DIVISOR_INDIVIDUAL)
        copia.update(plano_id=novo_id, versao=1, motivo=_MOTIVO, criado_por="migracao", aprovado_por="po:2026-11-10",
                     aprovado_em=agora, valido_de=agora, valido_ate=None)
        conexao.execute(sa.insert(configs).values(copia))


def downgrade() -> None:
    conexao = op.get_bind()
    plano = sa.Table("plano", sa.MetaData(), autoload_with=conexao)
    licenca = sa.table("licenca", sa.column("plano_id", sa.Integer))
    configs = sa.table("enriquecimento_config_plano", sa.column("plano_id", sa.Integer))
    for nome, *_ in _NOVOS:
        linha = conexao.execute(sa.select(plano.c.id).where(plano.c.nome == nome)).first()
        if linha is None:
            continue
        if conexao.execute(sa.select(licenca.c.plano_id).where(licenca.c.plano_id == linha[0])).first() is None:
            conexao.execute(sa.delete(configs).where(configs.c.plano_id == linha[0]))
            conexao.execute(sa.delete(plano).where(plano.c.id == linha[0]))
