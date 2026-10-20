"""Retentativa limitada na fila de enriquecimento (IA indisponível não pode perder a conta da fila).

Revision ID: e5b7d9f1a3c5
Revises: d2e4f6a8b0c2
Create Date: 2026-10-20
"""
from alembic import op
import sqlalchemy as sa

revision = "e5b7d9f1a3c5"
down_revision = "d2e4f6a8b0c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("fila_enriquecimento_conta") as batch_op:
        batch_op.add_column(sa.Column("tentativas", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("proxima_tentativa_em", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("fila_enriquecimento_conta") as batch_op:
        batch_op.drop_column("proxima_tentativa_em")
        batch_op.drop_column("tentativas")
