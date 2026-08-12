"""Campanhas (e-mail/WhatsApp em massa, separado da cadência)

Revision ID: e3275280ce74
Revises: b7e2c4f890a1
Create Date: 2026-08-12 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3275280ce74'
down_revision: Union[str, Sequence[str], None] = 'b7e2c4f890a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'campanha',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('nome', sa.String(), nullable=False),
        sa.Column('tipo', sa.String(), nullable=False),
        sa.Column('canais', sa.JSON(), nullable=False),
        sa.Column('assunto', sa.String(), nullable=True),
        sa.Column('conteudo_email', sa.String(), nullable=True),
        sa.Column('template_whatsapp_id', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='rascunho'),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('atualizado_em', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_campanha_tenant_id', 'campanha', ['tenant_id'])

    op.create_table(
        'campanha_destinatario',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('campanha_id', sa.Integer(), sa.ForeignKey('campanha.id'), nullable=False),
        sa.Column('decisor_id', sa.Integer(), sa.ForeignKey('decisor.id'), nullable=True),
        sa.Column('nome', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('telefone', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False, server_default='pendente'),
        sa.Column('enviado_em', sa.DateTime(), nullable=True),
        sa.Column('motivo_falha', sa.String(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index('ix_campanha_destinatario_tenant_id', 'campanha_destinatario', ['tenant_id'])
    op.create_index('ix_campanha_destinatario_campanha_id', 'campanha_destinatario', ['campanha_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_campanha_destinatario_campanha_id', table_name='campanha_destinatario')
    op.drop_index('ix_campanha_destinatario_tenant_id', table_name='campanha_destinatario')
    op.drop_table('campanha_destinatario')
    op.drop_index('ix_campanha_tenant_id', table_name='campanha')
    op.drop_table('campanha')
