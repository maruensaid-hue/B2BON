"""Esqueci minha senha - tabela redefinicao_senha

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-09-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d5e6f7a8b9'
down_revision: Union[str, Sequence[str], None] = 'b3c4d5e6f7a8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'redefinicao_senha',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=False),
        sa.Column('token', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='disponivel'),
        sa.Column('validade_em', sa.DateTime(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_redefinicao_senha_usuario_id', 'redefinicao_senha', ['usuario_id'])
    op.create_index('ix_redefinicao_senha_token', 'redefinicao_senha', ['token'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_redefinicao_senha_token', table_name='redefinicao_senha')
    op.drop_index('ix_redefinicao_senha_usuario_id', table_name='redefinicao_senha')
    op.drop_table('redefinicao_senha')
