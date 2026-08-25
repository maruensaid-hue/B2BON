"""Campo ativo em tenant (desativação reversível)

Revision ID: ff8579321bae
Revises: e3dada140dcb
Create Date: 2026-08-24 22:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ff8579321bae'
down_revision: Union[str, Sequence[str], None] = 'e3dada140dcb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('tenant', sa.Column('ativo', sa.Boolean(), server_default='true', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('tenant', 'ativo')
