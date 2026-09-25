"""representante_e_comissao

Revision ID: ef93ae5bea74
Revises: e78f9073763e
Create Date: 2026-09-25 09:07:28.523844

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'ef93ae5bea74'
down_revision: Union[str, Sequence[str], None] = 'e78f9073763e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'representante',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('nome', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('cpf', sa.String(), nullable=True),
        sa.Column('chave_pix', sa.String(), nullable=False),
        sa.Column('percentual_comissao', sa.Float(), nullable=False),
        sa.Column('ativo', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_representante_email'), 'representante', ['email'], unique=True)

    op.create_table(
        'comissao_representante',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('representante_id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('pagamento_licenca_id', sa.Integer(), nullable=False),
        sa.Column('valor_comissao', sa.Float(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('motivo_falha', sa.String(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.text('(CURRENT_TIMESTAMP)'), nullable=False),
        sa.Column('pago_em', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['representante_id'], ['representante.id'], ),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ),
        sa.ForeignKeyConstraint(['pagamento_licenca_id'], ['pagamento_licenca.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pagamento_licenca_id'),
    )
    op.create_index(
        op.f('ix_comissao_representante_representante_id'), 'comissao_representante', ['representante_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_comissao_representante_tenant_id'), 'comissao_representante', ['tenant_id'], unique=False,
    )

    with op.batch_alter_table('tenant') as batch_op:
        batch_op.add_column(sa.Column('representante_id', sa.Integer(), nullable=True))
        batch_op.create_foreign_key('fk_tenant_representante_id', 'representante', ['representante_id'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('tenant') as batch_op:
        batch_op.drop_constraint('fk_tenant_representante_id', type_='foreignkey')
        batch_op.drop_column('representante_id')

    op.drop_index(op.f('ix_comissao_representante_tenant_id'), table_name='comissao_representante')
    op.drop_index(op.f('ix_comissao_representante_representante_id'), table_name='comissao_representante')
    op.drop_table('comissao_representante')

    op.drop_index(op.f('ix_representante_email'), table_name='representante')
    op.drop_table('representante')
