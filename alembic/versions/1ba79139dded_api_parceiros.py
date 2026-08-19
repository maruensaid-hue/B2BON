"""API de parceiros: chave de API + webhooks de saida (Fase 2 hierarquia)

Revision ID: 1ba79139dded
Revises: d29ee2efce52
Create Date: 2026-08-19 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1ba79139dded'
down_revision: Union[str, Sequence[str], None] = 'd29ee2efce52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'chave_api_parceiro',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenant.id'), nullable=False, index=True),
        sa.Column('nome', sa.String(), nullable=False),
        sa.Column('prefixo', sa.String(), nullable=False),
        sa.Column('chave_hash', sa.String(), nullable=False, unique=True, index=True),
        sa.Column('criado_por_usuario_id', sa.Integer(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('ultimo_uso_em', sa.DateTime(), nullable=True),
        sa.Column('revogada_em', sa.DateTime(), nullable=True),
    )

    op.create_table(
        'assinatura_webhook_parceiro',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenant.id'), nullable=False, index=True),
        sa.Column('url_callback', sa.String(), nullable=False),
        sa.Column('segredo', sa.String(), nullable=False),
        sa.Column('ativa', sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('tenant_id'),
    )

    op.create_table(
        'evento_webhook_parceiro',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('assinatura_id', sa.Integer(), sa.ForeignKey('assinatura_webhook_parceiro.id'), nullable=False, index=True),
        sa.Column('tipo_evento', sa.String(), nullable=False),
        sa.Column('payload_json', sa.Text(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('tentativas', sa.Integer(), server_default='0', nullable=False),
        sa.Column('proxima_tentativa_em', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('entregue_em', sa.DateTime(), nullable=True),
        sa.Column('desistido_em', sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('evento_webhook_parceiro')
    op.drop_table('assinatura_webhook_parceiro')
    op.drop_table('chave_api_parceiro')
