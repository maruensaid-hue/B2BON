"""bounce de e-mail por contato (mensagem/campanha_destinatario)

Revision ID: f7c1a9e02b3d
Revises: d3982ab824f0
Create Date: 2026-09-16
"""

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "f7c1a9e02b3d"
down_revision: Union[str, Sequence[str], None] = "d3982ab824f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("mensagem", sa.Column("bounce_em", sa.DateTime(), nullable=True))
    op.add_column("mensagem", sa.Column("motivo_bounce", sa.String(), nullable=True))
    op.add_column("campanha_destinatario", sa.Column("bounce_em", sa.DateTime(), nullable=True))
    op.add_column("campanha_destinatario", sa.Column("motivo_bounce", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("campanha_destinatario", "motivo_bounce")
    op.drop_column("campanha_destinatario", "bounce_em")
    op.drop_column("mensagem", "motivo_bounce")
    op.drop_column("mensagem", "bounce_em")
