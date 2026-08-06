"""Pagamento de licenca via Mercado Pago (cadastro self-service com plano)

Revision ID: f19b3d6a7c52
Revises: e4a2c8f930d1
Create Date: 2026-08-06 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f19b3d6a7c52'
down_revision: Union[str, Sequence[str], None] = 'e4a2c8f930d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'pagamento_licenca',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('plano_id', sa.Integer(), sa.ForeignKey('plano.id'), nullable=False),
        sa.Column('preferencia_id_externo', sa.String(), nullable=False),
        sa.Column('pagamento_id_externo', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('valor', sa.Float(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('confirmado_em', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_pagamento_licenca_tenant_id', 'pagamento_licenca', ['tenant_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_pagamento_licenca_tenant_id', table_name='pagamento_licenca')
    op.drop_table('pagamento_licenca')
