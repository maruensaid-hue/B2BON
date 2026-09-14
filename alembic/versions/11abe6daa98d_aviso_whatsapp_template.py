"""Tenant.aviso_whatsapp_template_confirmado - dispensa o aviso de template

Revision ID: 11abe6daa98d
Revises: 32e487955942
Create Date: 2026-09-14 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '11abe6daa98d'
down_revision: Union[str, Sequence[str], None] = '32e487955942'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'tenant',
        sa.Column('aviso_whatsapp_template_confirmado', sa.Boolean(), server_default='false', nullable=False),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('tenant', 'aviso_whatsapp_template_confirmado')
