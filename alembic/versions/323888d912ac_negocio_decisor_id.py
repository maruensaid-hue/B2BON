"""Negocio ganha decisor_id (contato responsavel pela oportunidade)

Revision ID: 323888d912ac
Revises: b265e1b12928
Create Date: 2026-08-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '323888d912ac'
down_revision: Union[str, Sequence[str], None] = 'b265e1b12928'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('negocio') as batch_op:
        batch_op.add_column(sa.Column('decisor_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_negocio_decisor_id', 'decisor', ['decisor_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('negocio') as batch_op:
        batch_op.drop_constraint('fk_negocio_decisor_id', type_='foreignkey')
        batch_op.drop_column('decisor_id')
