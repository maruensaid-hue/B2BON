"""Cadencia.cancelar_ao_responder + Usuario.whatsapp_pessoal

Revision ID: d3982ab824f0
Revises: 36dacd3c57d0
Create Date: 2026-09-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd3982ab824f0'
down_revision: Union[str, Sequence[str], None] = '36dacd3c57d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'cadencia', sa.Column('cancelar_ao_responder', sa.Boolean(), server_default='false', nullable=False)
    )
    op.add_column('usuario', sa.Column('whatsapp_pessoal', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('usuario', 'whatsapp_pessoal')
    op.drop_column('cadencia', 'cancelar_ao_responder')
