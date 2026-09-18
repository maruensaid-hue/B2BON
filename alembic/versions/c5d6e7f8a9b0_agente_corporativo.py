"""Corporate AI Agent - Fase 6A (master prompt secao 57-58)

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
Create Date: 2026-09-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c5d6e7f8a9b0'
down_revision: Union[str, Sequence[str], None] = 'b4c5d6e7f8a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'configuracao_agente_corporativo',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('modo', sa.String(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('atualizado_em', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id'),
    )
    op.create_index(
        op.f('ix_configuracao_agente_corporativo_tenant_id'),
        'configuracao_agente_corporativo',
        ['tenant_id'],
    )

    op.create_table(
        'pergunta_agente_corporativo',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id_alvo', sa.String(), nullable=False),
        sa.Column('tenant_id_perguntante', sa.String(), nullable=False),
        sa.Column('pergunta', sa.String(), nullable=False),
        sa.Column('resposta_rascunho', sa.String(), nullable=True),
        sa.Column('resposta_final', sa.String(), nullable=True),
        sa.Column('evidencias', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('respondido_em', sa.DateTime(), nullable=True),
        sa.Column('respondido_por', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id_alvo'], ['tenant.id']),
        sa.ForeignKeyConstraint(['tenant_id_perguntante'], ['tenant.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_pergunta_agente_corporativo_tenant_id_alvo'),
        'pergunta_agente_corporativo',
        ['tenant_id_alvo'],
    )
    op.create_index(
        op.f('ix_pergunta_agente_corporativo_tenant_id_perguntante'),
        'pergunta_agente_corporativo',
        ['tenant_id_perguntante'],
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_pergunta_agente_corporativo_tenant_id_perguntante'), table_name='pergunta_agente_corporativo')
    op.drop_index(op.f('ix_pergunta_agente_corporativo_tenant_id_alvo'), table_name='pergunta_agente_corporativo')
    op.drop_table('pergunta_agente_corporativo')
    op.drop_index(op.f('ix_configuracao_agente_corporativo_tenant_id'), table_name='configuracao_agente_corporativo')
    op.drop_table('configuracao_agente_corporativo')
