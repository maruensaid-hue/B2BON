"""Verificacao de empresa - Company Claim/Trust Layer (master prompt Fase 1B)

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-09-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, Sequence[str], None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'verificacao_empresa',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='pendente'),
        sa.Column('email_verificacao', sa.String(), nullable=False),
        sa.Column('dominio_confere', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('cnpj_encontrado_receita', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('solicitado_por', sa.String(), nullable=True),
        sa.Column('solicitado_em', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('revisado_por', sa.String(), nullable=True),
        sa.Column('revisado_em', sa.DateTime(), nullable=True),
        sa.Column('motivo_rejeicao', sa.String(), nullable=True),
    )
    op.create_index('ix_verificacao_empresa_tenant_id', 'verificacao_empresa', ['tenant_id'])


def downgrade() -> None:
    op.drop_index('ix_verificacao_empresa_tenant_id', table_name='verificacao_empresa')
    op.drop_table('verificacao_empresa')
