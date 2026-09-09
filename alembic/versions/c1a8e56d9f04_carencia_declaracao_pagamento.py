"""Carencia de pagamento: declaracao e idempotencia de lembrete

Revision ID: c1a8e56d9f04
Revises: b56bb69a0ab0
Create Date: 2026-09-09 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1a8e56d9f04'
down_revision: Union[str, Sequence[str], None] = 'b56bb69a0ab0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('licenca', sa.Column('declaracao_pagamento_em', sa.DateTime(), nullable=True))
    op.add_column('licenca', sa.Column('ultimo_lembrete_cobranca_em', sa.Date(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('licenca', 'ultimo_lembrete_cobranca_em')
    op.drop_column('licenca', 'declaracao_pagamento_em')
