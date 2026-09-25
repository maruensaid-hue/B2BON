"""Opportunity Intelligence - Fase 6 do Master Prompt v4

Offer Intelligence (§25) como colunas da `oferta` (listas em JSON) e a
tabela `necessidade_oportunidade`: necessidades do cliente extraidas de
reuniao por IA (sempre SUGERIDA ate um humano confirmar) ou registradas
pelo vendedor, cada uma com a citacao literal da fonte.

Revision ID: a8390a098f04
Revises: f892ebf6e6f9
Create Date: 2026-09-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a8390a098f04'
down_revision: Union[str, Sequence[str], None] = 'f892ebf6e6f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LISTAS = (
    "problemas_resolvidos",
    "dores",
    "casos_uso",
    "personas",
    "industrias",
    "requisitos",
    "prerequisitos",
    "incompatibilidades",
    "objecoes",
    "cases",
    "cross_sell",
    "upsell",
    "bundles",
    "perguntas_descoberta",
    "criterios_qualificacao",
)


def upgrade() -> None:
    with op.batch_alter_table("oferta") as batch:
        batch.add_column(sa.Column("categoria", sa.String(), nullable=True))
        for nome in _LISTAS:
            batch.add_column(sa.Column(nome, sa.JSON(), nullable=True))
        batch.add_column(sa.Column("modelo_precificacao", sa.String(), nullable=True))
        batch.add_column(sa.Column("ticket_medio", sa.Float(), nullable=True))
        batch.add_column(sa.Column("margem_media", sa.Float(), nullable=True))
        batch.add_column(sa.Column("playbook", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column("disponivel_para_venda", sa.Boolean(), nullable=False, server_default=sa.true())
        )

    op.create_table(
        "necessidade_oportunidade",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False, index=True),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocio.id"), nullable=False, index=True),
        sa.Column("conta_id", sa.Integer(), sa.ForeignKey("conta.id"), nullable=False, index=True),
        sa.Column("categoria", sa.String(), nullable=False),
        sa.Column("descricao", sa.String(), nullable=False),
        sa.Column("citacao", sa.Text(), nullable=True),
        sa.Column("fonte_tipo", sa.String(), nullable=False),
        sa.Column("fonte_id", sa.Integer(), nullable=True),
        sa.Column("origem", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("registro_uso_ia_correlation_id", sa.String(), nullable=True),
        sa.Column("criado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
        sa.Column("revisado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
        sa.Column("revisado_em", sa.DateTime(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("necessidade_oportunidade")
    with op.batch_alter_table("oferta") as batch:
        batch.drop_column("disponivel_para_venda")
        batch.drop_column("playbook")
        batch.drop_column("margem_media")
        batch.drop_column("ticket_medio")
        batch.drop_column("modelo_precificacao")
        for nome in reversed(_LISTAS):
            batch.drop_column(nome)
        batch.drop_column("categoria")
