"""Business Intent - Fase 3A (master prompt secao 46-47)

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-09-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9d0e1f2a3b4'
down_revision: Union[str, Sequence[str], None] = 'b8c9d0e1f2a3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'intent',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('categoria', sa.String(), nullable=False),
        sa.Column('titulo', sa.String(), nullable=False),
        sa.Column('descricao', sa.String(), nullable=False),
        sa.Column('requisitos', sa.JSON(), nullable=True),
        sa.Column('faixa_orcamento', sa.String(), nullable=True),
        sa.Column('localizacao', sa.String(), nullable=True),
        sa.Column('prazo', sa.DateTime(), nullable=True),
        sa.Column('perfil_fornecedor_desejado', sa.String(), nullable=True),
        sa.Column('visibilidade', sa.String(), server_default='publica'),
        sa.Column('status', sa.String(), server_default='aberta'),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('expira_em', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_intent_tenant_id', 'intent', ['tenant_id'])


def downgrade() -> None:
    op.drop_index('ix_intent_tenant_id', table_name='intent')
    op.drop_table('intent')
