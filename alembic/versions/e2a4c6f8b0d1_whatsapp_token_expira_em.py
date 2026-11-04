"""Validade do token do WhatsApp (o do cadastro incorporado da Meta vence em 60 dias).

Revision ID: e2a4c6f8b0d1
Revises: d1f3a5c7e9b2
Create Date: 2026-11-04
"""
from alembic import op
import sqlalchemy as sa

revision = "e2a4c6f8b0d1"
down_revision = "d1f3a5c7e9b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("configuracao_whatsapp") as batch:
        batch.add_column(sa.Column("token_expira_em", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("configuracao_whatsapp") as batch:
        batch.drop_column("token_expira_em")
