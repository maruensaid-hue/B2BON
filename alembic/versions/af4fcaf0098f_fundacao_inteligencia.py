"""Fundacao de inteligencia (AI Gateway, Corporate Brain, perfis, aprendizado) - Fase 4 do Master Prompt v4

Revision ID: af4fcaf0098f
Revises: 494a19ef8c61
Create Date: 2026-09-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'af4fcaf0098f'
down_revision: Union[str, Sequence[str], None] = '494a19ef8c61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def _novas_colunas() -> list[sa.Column]:
    return [
    sa.Column('usuario_id', sa.Integer(), nullable=True),
    sa.Column('modulo', sa.String(), nullable=True),
    sa.Column('feature', sa.String(), nullable=True),
    sa.Column('workflow', sa.String(), nullable=True),
    sa.Column('provider', sa.String(), nullable=True),
    sa.Column('classe_modelo', sa.String(), nullable=True),
    sa.Column('gatilho', sa.String(), nullable=True),
    sa.Column('tokens_cache_leitura', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('tokens_cache_escrita', sa.Integer(), nullable=False, server_default='0'),
    sa.Column('status', sa.String(), nullable=False, server_default='sucesso'),
    sa.Column('erro', sa.String(), nullable=True),
    sa.Column('correlation_id', sa.String(), nullable=True),
    ]


def upgrade() -> None:
    with op.batch_alter_table('registro_uso_ia') as batch:
        for coluna in _novas_colunas():
            batch.add_column(coluna)
    op.create_index('ix_registro_uso_ia_modulo', 'registro_uso_ia', ['modulo'])
    op.create_index('ix_registro_uso_ia_feature', 'registro_uso_ia', ['feature'])

    op.create_table(
        'conhecimento_corporativo',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('tipo', sa.String(), nullable=False),
        sa.Column('titulo', sa.String(), nullable=False),
        sa.Column('conteudo', sa.Text(), nullable=False),
        sa.Column('origem', sa.String(), nullable=False, server_default='INTERNAL'),
        sa.Column('classificacao', sa.String(), nullable=False, server_default='INTERNAL'),
        sa.Column('visibilidade', sa.String(), nullable=False, server_default='interno'),
        sa.Column('fonte', sa.String(), nullable=True),
        sa.Column('evidencia', sa.JSON(), nullable=False),
        sa.Column('ativo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('criado_por_usuario_id', sa.Integer(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('atualizado_em', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_conhecimento_corporativo_tenant_id', 'conhecimento_corporativo', ['tenant_id'])
    op.create_index('ix_conhecimento_corporativo_tipo', 'conhecimento_corporativo', ['tipo'])

    op.create_table(
        'perfil_inteligencia',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('escopo', sa.String(), nullable=False),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('dados', sa.JSON(), nullable=False),
        sa.Column('fontes', sa.JSON(), nullable=False),
        sa.Column('versao', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('atualizado_em', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'escopo', 'usuario_id'),
    )
    op.create_index('ix_perfil_inteligencia_tenant_id', 'perfil_inteligencia', ['tenant_id'])

    op.create_table(
        'evento_aprendizado',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('feature', sa.String(), nullable=False),
        sa.Column('tipo', sa.String(), nullable=False),
        sa.Column('entidade_tipo', sa.String(), nullable=True),
        sa.Column('entidade_id', sa.Integer(), nullable=True),
        sa.Column('usuario_id', sa.Integer(), nullable=True),
        sa.Column('dados', sa.JSON(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_evento_aprendizado_tenant_id', 'evento_aprendizado', ['tenant_id'])
    op.create_index('ix_evento_aprendizado_feature', 'evento_aprendizado', ['feature'])


def downgrade() -> None:
    op.drop_index('ix_evento_aprendizado_feature', table_name='evento_aprendizado')
    op.drop_index('ix_evento_aprendizado_tenant_id', table_name='evento_aprendizado')
    op.drop_table('evento_aprendizado')
    op.drop_index('ix_perfil_inteligencia_tenant_id', table_name='perfil_inteligencia')
    op.drop_table('perfil_inteligencia')
    op.drop_index('ix_conhecimento_corporativo_tipo', table_name='conhecimento_corporativo')
    op.drop_index('ix_conhecimento_corporativo_tenant_id', table_name='conhecimento_corporativo')
    op.drop_table('conhecimento_corporativo')
    op.drop_index('ix_registro_uso_ia_feature', table_name='registro_uso_ia')
    op.drop_index('ix_registro_uso_ia_modulo', table_name='registro_uso_ia')
    with op.batch_alter_table('registro_uso_ia') as batch:
        for coluna in reversed(_novas_colunas()):
            batch.drop_column(coluna.name)
