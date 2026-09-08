"""Rótulos configuráveis por tipo de tenant na hierarquia (Master/Vendedor/Cliente)

Revision ID: 38c04a0de37e
Revises: 0363630be266
Create Date: 2026-09-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '38c04a0de37e'
down_revision: Union[str, Sequence[str], None] = '0363630be266'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'rotulo_tipo_tenant',
        sa.Column('tipo', sa.String(), nullable=False),
        sa.Column('rotulo', sa.String(), nullable=False),
        sa.PrimaryKeyConstraint('tipo'),
    )
    tabela = sa.table(
        'rotulo_tipo_tenant',
        sa.column('tipo', sa.String()),
        sa.column('rotulo', sa.String()),
    )
    op.bulk_insert(
        tabela,
        [
            {'tipo': 'distribuidor', 'rotulo': 'Master'},
            {'tipo': 'revendedor', 'rotulo': 'Vendedor'},
            {'tipo': 'cliente', 'rotulo': 'Cliente'},
        ],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('rotulo_tipo_tenant')
