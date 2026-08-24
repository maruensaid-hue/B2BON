"""Lista de prospeccao nomeada (cargos-alvo + import desacoplado de ICP)

Revision ID: e3dada140dcb
Revises: b214d51bf528
Create Date: 2026-08-24 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3dada140dcb'
down_revision: Union[str, Sequence[str], None] = 'b214d51bf528'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'lista_prospeccao',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('nome', sa.String(), nullable=False),
        sa.Column('icp_id', sa.Integer(), nullable=True),
        sa.Column('cargos_alvo', sa.JSON(), nullable=True),
        sa.Column('criado_por_usuario_id', sa.Integer(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['icp_id'], ['icp.id']),
        sa.ForeignKeyConstraint(['criado_por_usuario_id'], ['usuario.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_lista_prospeccao_tenant_id'), 'lista_prospeccao', ['tenant_id'])
    op.add_column('conta', sa.Column('lista_prospeccao_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_conta_lista_prospeccao_id', 'conta', 'lista_prospeccao', ['lista_prospeccao_id'], ['id']
    )


def downgrade() -> None:
    op.drop_constraint('fk_conta_lista_prospeccao_id', 'conta', type_='foreignkey')
    op.drop_column('conta', 'lista_prospeccao_id')
    op.drop_index(op.f('ix_lista_prospeccao_tenant_id'), table_name='lista_prospeccao')
    op.drop_table('lista_prospeccao')
