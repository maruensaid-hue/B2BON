"""Leads sem ICP — icp_id opcional na conta e proximo_passo

Revision ID: c7d4e91a5f13
Revises: b3f7d1a9c204
Create Date: 2026-08-06 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c7d4e91a5f13'
down_revision: Union[str, Sequence[str], None] = 'b3f7d1a9c204'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('conta') as batch_op:
        batch_op.alter_column('icp_id', existing_type=sa.Integer(), nullable=True)
    op.add_column('conta', sa.Column('proximo_passo', sa.String(), nullable=True))
    op.add_column('conta', sa.Column('proximo_passo_em', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('conta', 'proximo_passo_em')
    op.drop_column('conta', 'proximo_passo')
    with op.batch_alter_table('conta') as batch_op:
        batch_op.alter_column('icp_id', existing_type=sa.Integer(), nullable=False)
