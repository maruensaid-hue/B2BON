"""Atividade ganha conta_id (negocio_id vira opcional) + Conta.resumo_site/observacoes

Revision ID: b265e1b12928
Revises: 4d1d0fcb9df5
Create Date: 2026-08-12 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b265e1b12928'
down_revision: Union[str, Sequence[str], None] = '4d1d0fcb9df5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('atividade') as batch_op:
        batch_op.add_column(sa.Column('conta_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_atividade_conta_id', 'conta', ['conta_id'], ['id'])
        batch_op.create_index('ix_atividade_conta_id', ['conta_id'])
        batch_op.alter_column('negocio_id', existing_type=sa.Integer(), nullable=True)

    op.add_column('conta', sa.Column('resumo_site', sa.Text(), nullable=True))
    op.add_column('conta', sa.Column('observacoes', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('conta', 'observacoes')
    op.drop_column('conta', 'resumo_site')

    with op.batch_alter_table('atividade') as batch_op:
        batch_op.alter_column('negocio_id', existing_type=sa.Integer(), nullable=False)
        batch_op.drop_index('ix_atividade_conta_id')
        batch_op.drop_constraint('fk_atividade_conta_id', type_='foreignkey')
        batch_op.drop_column('conta_id')
