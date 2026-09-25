"""Outbox de eventos de dominio - Fase 2 do Master Prompt v4 (secao 77)

Revision ID: 1ca76a6cdfbc
Revises: bd1685385a43
Create Date: 2026-09-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '1ca76a6cdfbc'
down_revision: Union[str, Sequence[str], None] = 'bd1685385a43'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'evento_dominio',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('evento_id', sa.String(), nullable=False),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('tipo', sa.String(), nullable=False),
        sa.Column('versao', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('agregado_tipo', sa.String(), nullable=False),
        sa.Column('agregado_id', sa.String(), nullable=False),
        sa.Column('ator_id', sa.String(), nullable=True),
        sa.Column('classificacao', sa.String(), nullable=False, server_default='INTERNAL'),
        sa.Column('correlation_id', sa.String(), nullable=True),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('ocorrido_em', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('processado_em', sa.DateTime(), nullable=True),
        sa.Column('tentativas', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('ultimo_erro', sa.String(), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('evento_id'),
    )
    op.create_index(op.f('ix_evento_dominio_tenant_id'), 'evento_dominio', ['tenant_id'])
    op.create_index(op.f('ix_evento_dominio_tipo'), 'evento_dominio', ['tipo'])
    op.create_index(op.f('ix_evento_dominio_processado_em'), 'evento_dominio', ['processado_em'])


def downgrade() -> None:
    op.drop_index(op.f('ix_evento_dominio_processado_em'), table_name='evento_dominio')
    op.drop_index(op.f('ix_evento_dominio_tipo'), table_name='evento_dominio')
    op.drop_index(op.f('ix_evento_dominio_tenant_id'), table_name='evento_dominio')
    op.drop_table('evento_dominio')
