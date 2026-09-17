"""Relacionamento empresarial - Business Graph foundation (master prompt Fase 1D)

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, Sequence[str], None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'relacionamento_empresarial',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id_origem', sa.String(), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('tenant_id_destino', sa.String(), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('tipo', sa.String(), nullable=False),
        sa.Column('visibilidade', sa.String(), nullable=False, server_default='publica'),
        sa.Column('confianca', sa.String(), nullable=False, server_default='autodeclarada'),
        sa.Column('criado_por', sa.String(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('metadados', sa.JSON(), nullable=False, server_default='{}'),
    )
    op.create_index('ix_relacionamento_empresarial_tenant_id_origem', 'relacionamento_empresarial', ['tenant_id_origem'])
    op.create_index('ix_relacionamento_empresarial_tenant_id_destino', 'relacionamento_empresarial', ['tenant_id_destino'])


def downgrade() -> None:
    op.drop_index('ix_relacionamento_empresarial_tenant_id_destino', table_name='relacionamento_empresarial')
    op.drop_index('ix_relacionamento_empresarial_tenant_id_origem', table_name='relacionamento_empresarial')
    op.drop_table('relacionamento_empresarial')
