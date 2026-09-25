"""Fundacao de API e Integration Hub - Fase 3 do Master Prompt v4

Chaves de API por tenant, idempotencia, webhooks de saida de eventos de
dominio, conexoes do Integration Hub e execucoes de sync.

Revision ID: 494a19ef8c61
Revises: 1ca76a6cdfbc
Create Date: 2026-09-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '494a19ef8c61'
down_revision: Union[str, Sequence[str], None] = '1ca76a6cdfbc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'chave_api_tenant',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('nome', sa.String(), nullable=False),
        sa.Column('prefixo', sa.String(), nullable=False),
        sa.Column('chave_hash', sa.String(), nullable=False),
        sa.Column('escopos', sa.JSON(), nullable=False),
        sa.Column('criado_por_usuario_id', sa.Integer(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('ultimo_uso_em', sa.DateTime(), nullable=True),
        sa.Column('revogada_em', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('chave_hash'),
    )
    op.create_index('ix_chave_api_tenant_tenant_id', 'chave_api_tenant', ['tenant_id'])

    op.create_table(
        'registro_idempotencia',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('chave', sa.String(), nullable=False),
        sa.Column('rota', sa.String(), nullable=False),
        sa.Column('hash_corpo', sa.String(), nullable=False),
        sa.Column('status_code', sa.Integer(), nullable=False),
        sa.Column('resposta', sa.JSON(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id', 'chave'),
    )
    op.create_index('ix_registro_idempotencia_tenant_id', 'registro_idempotencia', ['tenant_id'])

    op.create_table(
        'assinatura_webhook_tenant',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('url', sa.String(), nullable=False),
        sa.Column('eventos', sa.JSON(), nullable=False),
        sa.Column('segredo', sa.String(), nullable=False),
        sa.Column('ativa', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_assinatura_webhook_tenant_tenant_id', 'assinatura_webhook_tenant', ['tenant_id'])

    op.create_table(
        'entrega_webhook',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('assinatura_id', sa.Integer(), sa.ForeignKey('assinatura_webhook_tenant.id'), nullable=False),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('evento_id', sa.String(), nullable=False),
        sa.Column('tipo', sa.String(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='pendente'),
        sa.Column('tentativas', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('proxima_tentativa_em', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('ultimo_status_http', sa.Integer(), nullable=True),
        sa.Column('ultimo_erro', sa.String(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('entregue_em', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('assinatura_id', 'evento_id'),
    )
    op.create_index('ix_entrega_webhook_assinatura_id', 'entrega_webhook', ['assinatura_id'])
    op.create_index('ix_entrega_webhook_tenant_id', 'entrega_webhook', ['tenant_id'])

    op.create_table(
        'conexao_integracao',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('sistema', sa.String(), nullable=False),
        sa.Column('nome', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='ativa'),
        sa.Column('credenciais', sa.String(), nullable=True),
        sa.Column('configuracao', sa.JSON(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('ultimo_sync_em', sa.DateTime(), nullable=True),
        sa.Column('ultimo_erro', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_conexao_integracao_tenant_id', 'conexao_integracao', ['tenant_id'])

    op.create_table(
        'execucao_sync',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('conexao_id', sa.Integer(), sa.ForeignKey('conexao_integracao.id'), nullable=False),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('entidade', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='executando'),
        sa.Column('incremental_desde', sa.DateTime(), nullable=True),
        sa.Column('itens_lidos', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('paginas', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('tentativas', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('iniciado_em', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('finalizado_em', sa.DateTime(), nullable=True),
        sa.Column('erro', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_execucao_sync_conexao_id', 'execucao_sync', ['conexao_id'])
    op.create_index('ix_execucao_sync_tenant_id', 'execucao_sync', ['tenant_id'])


def downgrade() -> None:
    op.drop_index('ix_execucao_sync_tenant_id', table_name='execucao_sync')
    op.drop_index('ix_execucao_sync_conexao_id', table_name='execucao_sync')
    op.drop_table('execucao_sync')
    op.drop_index('ix_conexao_integracao_tenant_id', table_name='conexao_integracao')
    op.drop_table('conexao_integracao')
    op.drop_index('ix_entrega_webhook_tenant_id', table_name='entrega_webhook')
    op.drop_index('ix_entrega_webhook_assinatura_id', table_name='entrega_webhook')
    op.drop_table('entrega_webhook')
    op.drop_index('ix_assinatura_webhook_tenant_tenant_id', table_name='assinatura_webhook_tenant')
    op.drop_table('assinatura_webhook_tenant')
    op.drop_index('ix_registro_idempotencia_tenant_id', table_name='registro_idempotencia')
    op.drop_table('registro_idempotencia')
    op.drop_index('ix_chave_api_tenant_tenant_id', table_name='chave_api_tenant')
    op.drop_table('chave_api_tenant')
