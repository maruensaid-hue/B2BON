"""link_captura_lead

Revision ID: e78f9073763e
Revises: 494a19ef8c61
Create Date: 2026-09-25 08:51:56.912374

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e78f9073763e'
down_revision: Union[str, Sequence[str], None] = '494a19ef8c61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'link_captura_lead',
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('codigo', sa.String(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ),
        sa.PrimaryKeyConstraint('tenant_id'),
    )
    op.create_index(op.f('ix_link_captura_lead_codigo'), 'link_captura_lead', ['codigo'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_link_captura_lead_codigo'), table_name='link_captura_lead')
    op.drop_table('link_captura_lead')
