"""Corporate Rooms + Channels + Messages - Fase 4A (master prompt secao 52-54)

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-09-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = 'd0e1f2a3b4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'sala_corporativa',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id_a', sa.String(), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('tenant_id_b', sa.String(), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('tenant_id_a', 'tenant_id_b'),
    )
    op.create_index('ix_sala_corporativa_tenant_id_a', 'sala_corporativa', ['tenant_id_a'])
    op.create_index('ix_sala_corporativa_tenant_id_b', 'sala_corporativa', ['tenant_id_b'])

    op.create_table(
        'canal_sala',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('sala_id', sa.Integer(), sa.ForeignKey('sala_corporativa.id'), nullable=False),
        sa.Column('tipo', sa.String(), nullable=False),
        sa.Column('nome', sa.String(), nullable=True),
        sa.Column('criado_por', sa.String(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_canal_sala_sala_id', 'canal_sala', ['sala_id'])

    op.create_table(
        'mensagem_sala',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('canal_id', sa.Integer(), sa.ForeignKey('canal_sala.id'), nullable=False),
        sa.Column('tenant_id_remetente', sa.String(), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('usuario_id', sa.Integer(), sa.ForeignKey('usuario.id'), nullable=True),
        sa.Column('texto', sa.String(), nullable=False),
        sa.Column('documento_url', sa.String(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_mensagem_sala_canal_id', 'mensagem_sala', ['canal_id'])


def downgrade() -> None:
    op.drop_index('ix_mensagem_sala_canal_id', table_name='mensagem_sala')
    op.drop_table('mensagem_sala')
    op.drop_index('ix_canal_sala_sala_id', table_name='canal_sala')
    op.drop_table('canal_sala')
    op.drop_index('ix_sala_corporativa_tenant_id_b', table_name='sala_corporativa')
    op.drop_index('ix_sala_corporativa_tenant_id_a', table_name='sala_corporativa')
    op.drop_table('sala_corporativa')
