"""Video + transcricao automatica na reuniao (bot de terceiro)

Revision ID: 2e7a6f9c0d70
Revises: 462223a769a5
Create Date: 2026-08-20 09:33:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2e7a6f9c0d70'
down_revision: Union[str, Sequence[str], None] = '462223a769a5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('reuniao', sa.Column('bot_id', sa.String(), nullable=True))
    op.add_column('reuniao', sa.Column('status_transcricao', sa.String(), nullable=True))
    op.add_column('reuniao', sa.Column('transcricao', sa.Text(), nullable=True))
    op.add_column('reuniao', sa.Column('resumo_ia', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('reuniao', 'resumo_ia')
    op.drop_column('reuniao', 'transcricao')
    op.drop_column('reuniao', 'status_transcricao')
    op.drop_column('reuniao', 'bot_id')
