"""Comentario e reacao em post - Fase 2C (master prompt secao 45)

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-09-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'comentario_post',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('post_id', sa.Integer(), sa.ForeignKey('post_rede_social.id'), nullable=False),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=False),
        sa.Column('texto', sa.String(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_comentario_post_post_id', 'comentario_post', ['post_id'])
    op.create_index('ix_comentario_post_tenant_id', 'comentario_post', ['tenant_id'])

    op.create_table(
        'reacao_post',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('post_id', sa.Integer(), sa.ForeignKey('post_rede_social.id'), nullable=False),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=False),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('post_id', 'tenant_id'),
    )
    op.create_index('ix_reacao_post_post_id', 'reacao_post', ['post_id'])
    op.create_index('ix_reacao_post_tenant_id', 'reacao_post', ['tenant_id'])


def downgrade() -> None:
    op.drop_index('ix_reacao_post_tenant_id', table_name='reacao_post')
    op.drop_index('ix_reacao_post_post_id', table_name='reacao_post')
    op.drop_table('reacao_post')
    op.drop_index('ix_comentario_post_tenant_id', table_name='comentario_post')
    op.drop_index('ix_comentario_post_post_id', table_name='comentario_post')
    op.drop_table('comentario_post')
