"""Buying Room (SalaCompra) + escopo do CanalSala - Fase 5A (master prompt secao 52-55)

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-09-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2a3b4c5d6e7'
down_revision: Union[str, Sequence[str], None] = 'e1f2a3b4c5d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('canal_sala', sa.Column('escopo', sa.String(), server_default='compartilhado', nullable=True))

    op.create_table(
        'sala_compra',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('sala_corporativa_id', sa.Integer(), sa.ForeignKey('sala_corporativa.id'), nullable=False),
        sa.Column('tenant_id_vendedor', sa.String(), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('negocio_id', sa.Integer(), sa.ForeignKey('negocio.id'), nullable=False),
        sa.Column('visivel_para_comprador', sa.Boolean(), server_default=sa.false()),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('sala_corporativa_id'),
    )
    op.create_index('ix_sala_compra_sala_corporativa_id', 'sala_compra', ['sala_corporativa_id'])


def downgrade() -> None:
    op.drop_index('ix_sala_compra_sala_corporativa_id', table_name='sala_compra')
    op.drop_table('sala_compra')
    op.drop_column('canal_sala', 'escopo')
