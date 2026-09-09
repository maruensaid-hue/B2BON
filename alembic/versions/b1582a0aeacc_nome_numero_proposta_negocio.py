"""Nome e número (sequencial por tenant) em proposta_negocio, para a busca global

Revision ID: b1582a0aeacc
Revises: 38c04a0de37e
Create Date: 2026-09-09 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1582a0aeacc'
down_revision: Union[str, Sequence[str], None] = '38c04a0de37e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('proposta_negocio', sa.Column('nome', sa.String(), nullable=True))
    op.add_column('proposta_negocio', sa.Column('numero', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('proposta_negocio', 'numero')
    op.drop_column('proposta_negocio', 'nome')
