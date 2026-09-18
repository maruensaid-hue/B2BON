"""Observabilidade de custo/latencia de IA - Fase 7C (master prompt secao 85)

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
Create Date: 2026-09-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd6e7f8a9b0c1'
down_revision: Union[str, Sequence[str], None] = 'c5d6e7f8a9b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'registro_uso_ia',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('agente', sa.String(), nullable=False),
        sa.Column('tokens_entrada', sa.Integer(), nullable=False),
        sa.Column('tokens_saida', sa.Integer(), nullable=False),
        sa.Column('latencia_ms', sa.Integer(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_registro_uso_ia_tenant_id'), 'registro_uso_ia', ['tenant_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_registro_uso_ia_tenant_id'), table_name='registro_uso_ia')
    op.drop_table('registro_uso_ia')
