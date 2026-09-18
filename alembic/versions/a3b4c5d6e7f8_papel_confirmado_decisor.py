"""Stakeholder Map - papel_confirmado no Decisor - Fase 5B (master prompt secao 27, 56)

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
Create Date: 2026-09-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3b4c5d6e7f8'
down_revision: Union[str, Sequence[str], None] = 'f2a3b4c5d6e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('decisor', sa.Column('papel_confirmado', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('decisor', 'papel_confirmado')
