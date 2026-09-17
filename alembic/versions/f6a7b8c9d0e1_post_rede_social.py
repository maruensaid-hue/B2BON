"""Post de rede social - Business Feed (master prompt Fase 2B)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-09-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, Sequence[str], None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'post_rede_social',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('usuario_autor_id', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=False),
        sa.Column('texto', sa.String(), nullable=False),
        sa.Column('imagem_url', sa.String(), nullable=True),
        sa.Column('link_url', sa.String(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_post_rede_social_tenant_id', 'post_rede_social', ['tenant_id'])


def downgrade() -> None:
    op.drop_index('ix_post_rede_social_tenant_id', table_name='post_rede_social')
    op.drop_table('post_rede_social')
