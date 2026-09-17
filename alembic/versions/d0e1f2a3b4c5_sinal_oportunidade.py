"""Sinal de Oportunidade - Fase 3D (master prompt secao 28, 50-51)

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-09-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd0e1f2a3b4c5'
down_revision: Union[str, Sequence[str], None] = 'c9d0e1f2a3b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'sinal_oportunidade',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('tenant_id_alvo', sa.String(), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('tipo_sinal', sa.String(), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('confianca', sa.String(), nullable=False),
        sa.Column('motivo', sa.String(), nullable=False),
        sa.Column('evidencias', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(), server_default='novo'),
        sa.Column('conta_id_gerada', sa.Integer(), sa.ForeignKey('conta.id'), nullable=True),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('expira_em', sa.DateTime(), nullable=True),
        sa.UniqueConstraint('tenant_id', 'tenant_id_alvo', 'tipo_sinal'),
    )
    op.create_index('ix_sinal_oportunidade_tenant_id', 'sinal_oportunidade', ['tenant_id'])
    op.create_index('ix_sinal_oportunidade_tenant_id_alvo', 'sinal_oportunidade', ['tenant_id_alvo'])


def downgrade() -> None:
    op.drop_index('ix_sinal_oportunidade_tenant_id_alvo', table_name='sinal_oportunidade')
    op.drop_index('ix_sinal_oportunidade_tenant_id', table_name='sinal_oportunidade')
    op.drop_table('sinal_oportunidade')
