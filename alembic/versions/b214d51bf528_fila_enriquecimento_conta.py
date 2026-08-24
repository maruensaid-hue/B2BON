"""Fila de enriquecimento em lote (site + decisores) pra importacao de planilha

Revision ID: b214d51bf528
Revises: 8dc3e8c6e767
Create Date: 2026-08-21 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b214d51bf528'
down_revision: Union[str, Sequence[str], None] = '8dc3e8c6e767'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'fila_enriquecimento_conta',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('conta_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='pendente'),
        sa.Column('erro', sa.String(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('processado_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id']),
        sa.ForeignKeyConstraint(['conta_id'], ['conta.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_fila_enriquecimento_conta_tenant_id'), 'fila_enriquecimento_conta', ['tenant_id'])
    op.create_index(op.f('ix_fila_enriquecimento_conta_conta_id'), 'fila_enriquecimento_conta', ['conta_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_fila_enriquecimento_conta_conta_id'), table_name='fila_enriquecimento_conta')
    op.drop_index(op.f('ix_fila_enriquecimento_conta_tenant_id'), table_name='fila_enriquecimento_conta')
    op.drop_table('fila_enriquecimento_conta')
