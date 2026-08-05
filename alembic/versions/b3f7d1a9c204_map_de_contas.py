"""MAP de contas — vendedor_usuario_id na conta e interacao_conta

Revision ID: b3f7d1a9c204
Revises: 9a1c7e2b4f80
Create Date: 2026-08-06 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b3f7d1a9c204'
down_revision: Union[str, Sequence[str], None] = '9a1c7e2b4f80'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('conta', sa.Column('vendedor_usuario_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_conta_vendedor_usuario_id', 'conta', 'usuario', ['vendedor_usuario_id'], ['id']
    )

    op.create_table(
        'interacao_conta',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('conta_id', sa.Integer(), sa.ForeignKey('conta.id'), nullable=False),
        sa.Column('tipo', sa.String(), nullable=False),
        sa.Column('descricao', sa.String(), nullable=True),
        sa.Column('criado_por_usuario_id', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=True),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_interacao_conta_tenant_id', 'interacao_conta', ['tenant_id'])
    op.create_index('ix_interacao_conta_conta_id', 'interacao_conta', ['conta_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_interacao_conta_conta_id', table_name='interacao_conta')
    op.drop_index('ix_interacao_conta_tenant_id', table_name='interacao_conta')
    op.drop_table('interacao_conta')
    op.drop_constraint('fk_conta_vendedor_usuario_id', 'conta', type_='foreignkey')
    op.drop_column('conta', 'vendedor_usuario_id')
