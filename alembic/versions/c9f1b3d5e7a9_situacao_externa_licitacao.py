"""Situação e última atualização do edital na fonte pública (cancelamento, suspensão, retificação) + contador de alterações na coleta.

Revision ID: c9f1b3d5e7a9
Revises: b8e0a2c4d6f8
Create Date: 2026-10-20
"""
from alembic import op
import sqlalchemy as sa

revision = "c9f1b3d5e7a9"
down_revision = "b8e0a2c4d6f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("licitacao") as batch_op:
        batch_op.add_column(sa.Column("situacao_externa", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("atualizado_externo_em", sa.DateTime(), nullable=True))
    with op.batch_alter_table("execucao_coleta_fonte") as batch_op:
        batch_op.add_column(sa.Column("alterados_na_fonte", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    with op.batch_alter_table("execucao_coleta_fonte") as batch_op:
        batch_op.drop_column("alterados_na_fonte")
    with op.batch_alter_table("licitacao") as batch_op:
        batch_op.drop_column("atualizado_externo_em")
        batch_op.drop_column("situacao_externa")
