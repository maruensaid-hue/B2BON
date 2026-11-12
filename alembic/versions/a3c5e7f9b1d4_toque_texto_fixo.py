"""Toque de cadencia com texto fixo: texto_fixo e assunto_fixo.

Quando o toque tem texto fixo, a geracao usa esse texto (com [Nome], [Nome completo] e [Empresa]) em vez de pedir a IA. Colunas novas e
anulaveis; nenhum dado muda e os toques existentes continuam com a IA.

Revision ID: a3c5e7f9b1d4
Revises: f6b8d0a2c4e1
Create Date: 2026-11-12
"""
import sqlalchemy as sa

from alembic import op

revision = "a3c5e7f9b1d4"
down_revision = "f6b8d0a2c4e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("toque_cadencia", sa.Column("texto_fixo", sa.Text(), nullable=True))
    op.add_column("toque_cadencia", sa.Column("assunto_fixo", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("toque_cadencia", "assunto_fixo")
    op.drop_column("toque_cadencia", "texto_fixo")
