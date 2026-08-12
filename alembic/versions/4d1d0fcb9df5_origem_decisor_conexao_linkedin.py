"""Origem do decisor + conexões de LinkedIn do vendedor

Revision ID: 4d1d0fcb9df5
Revises: e3275280ce74
Create Date: 2026-08-12 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4d1d0fcb9df5'
down_revision: Union[str, Sequence[str], None] = 'e3275280ce74'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('decisor', sa.Column('origem', sa.String(), nullable=True))

    op.create_table(
        'conexao_linkedin',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=False),
        sa.Column('nome_completo', sa.String(), nullable=False),
        sa.Column('url_perfil', sa.String(), nullable=True),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('empresa_atual', sa.String(), nullable=True),
        sa.Column('cargo_atual', sa.String(), nullable=True),
        sa.Column('conectado_em', sa.Date(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_conexao_linkedin_tenant_id', 'conexao_linkedin', ['tenant_id'])
    op.create_index('ix_conexao_linkedin_tenant_usuario', 'conexao_linkedin', ['tenant_id', 'usuario_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_conexao_linkedin_tenant_usuario', table_name='conexao_linkedin')
    op.drop_index('ix_conexao_linkedin_tenant_id', table_name='conexao_linkedin')
    op.drop_table('conexao_linkedin')
    op.drop_column('decisor', 'origem')
