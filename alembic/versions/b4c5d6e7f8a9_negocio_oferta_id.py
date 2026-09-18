"""Revenue Agent - Negocio.oferta_id - Fase 5D (master prompt secao 34, 76)

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-09-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b4c5d6e7f8a9'
down_revision: Union[str, Sequence[str], None] = 'a3b4c5d6e7f8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('negocio', sa.Column('oferta_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('negocio', 'oferta_id')
