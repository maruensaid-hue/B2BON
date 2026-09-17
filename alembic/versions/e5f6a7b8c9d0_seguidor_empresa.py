"""Seguidor de empresa - FOLLOWING (master prompt Fase 2A)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, Sequence[str], None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'seguidor_empresa',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id_seguidor', sa.String(), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('tenant_id_seguido', sa.String(), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('tenant_id_seguidor', 'tenant_id_seguido'),
    )
    op.create_index('ix_seguidor_empresa_tenant_id_seguidor', 'seguidor_empresa', ['tenant_id_seguidor'])
    op.create_index('ix_seguidor_empresa_tenant_id_seguido', 'seguidor_empresa', ['tenant_id_seguido'])


def downgrade() -> None:
    op.drop_index('ix_seguidor_empresa_tenant_id_seguido', table_name='seguidor_empresa')
    op.drop_index('ix_seguidor_empresa_tenant_id_seguidor', table_name='seguidor_empresa')
    op.drop_table('seguidor_empresa')
