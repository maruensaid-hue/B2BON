"""Notificacao da Rede Social - Fase 2D (master prompt secao 65)

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-09-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8c9d0e1f2a3'
down_revision: Union[str, Sequence[str], None] = 'a7b8c9d0e1f2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'notificacao_rede_social',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('tipo', sa.String(), nullable=False),
        sa.Column('referencia_tipo', sa.String(), nullable=False),
        sa.Column('referencia_id', sa.Integer(), nullable=False),
        sa.Column('mensagem', sa.String(), nullable=False),
        sa.Column('lida_em', sa.DateTime(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_notificacao_rede_social_tenant_id', 'notificacao_rede_social', ['tenant_id'])


def downgrade() -> None:
    op.drop_index('ix_notificacao_rede_social_tenant_id', table_name='notificacao_rede_social')
    op.drop_table('notificacao_rede_social')
