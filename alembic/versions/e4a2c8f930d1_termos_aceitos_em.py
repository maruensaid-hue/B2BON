"""Registro de aceite de termos/privacidade no cadastro

Revision ID: e4a2c8f930d1
Revises: d8e5f21b6a30
Create Date: 2026-08-06 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4a2c8f930d1'
down_revision: Union[str, Sequence[str], None] = 'd8e5f21b6a30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('usuario', sa.Column('termos_aceitos_em', sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('usuario', 'termos_aceitos_em')
