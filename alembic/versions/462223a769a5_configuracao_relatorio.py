"""Configuracao de relatorio periodico (Fase 3 hierarquia)

Revision ID: 462223a769a5
Revises: 1ba79139dded
Create Date: 2026-08-19 19:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '462223a769a5'
down_revision: Union[str, Sequence[str], None] = '1ba79139dded'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'configuracao_relatorio',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenant.id'), nullable=False, index=True),
        sa.Column('cadencia', sa.String(), server_default='desativada', nullable=False),
        sa.Column('ultimo_envio_em', sa.DateTime(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('tenant_id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('configuracao_relatorio')
