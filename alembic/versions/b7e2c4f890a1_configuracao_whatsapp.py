"""Configuracao de WhatsApp Business por tenant (raio-X de producao)

Revision ID: b7e2c4f890a1
Revises: f19b3d6a7c52
Create Date: 2026-08-07 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7e2c4f890a1'
down_revision: Union[str, Sequence[str], None] = 'f19b3d6a7c52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'configuracao_whatsapp',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.String(), nullable=False),
        sa.Column('access_token', sa.String(), nullable=False),
        sa.Column('phone_number_id', sa.String(), nullable=False),
        sa.Column('business_account_id', sa.String(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('atualizado_em', sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint('tenant_id'),
    )
    op.create_index('ix_configuracao_whatsapp_tenant_id', 'configuracao_whatsapp', ['tenant_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_configuracao_whatsapp_tenant_id', table_name='configuracao_whatsapp')
    op.drop_table('configuracao_whatsapp')
