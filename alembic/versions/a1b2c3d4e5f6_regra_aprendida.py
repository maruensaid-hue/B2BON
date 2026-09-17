"""Regras Aprendidas - loop de aprendizado (master prompt secoes 13/14)

Revision ID: a1b2c3d4e5f6
Revises: f7c1a9e02b3d
Create Date: 2026-09-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f7c1a9e02b3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'regra_aprendida',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('icp_id', sa.Integer(), sa.ForeignKey('icp.id'), nullable=True),
        sa.Column('oferta_id', sa.Integer(), sa.ForeignKey('oferta.id'), nullable=True),
        sa.Column('canal', sa.String(), nullable=True),
        sa.Column('regra', sa.String(), nullable=False),
        sa.Column('ativa', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('atualizado_em', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_regra_aprendida_tenant_id', 'regra_aprendida', ['tenant_id'])


def downgrade() -> None:
    op.drop_index('ix_regra_aprendida_tenant_id', table_name='regra_aprendida')
    op.drop_table('regra_aprendida')
