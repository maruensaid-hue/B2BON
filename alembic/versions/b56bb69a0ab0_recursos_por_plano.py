"""Recursos exclusivos por plano (gancho de upgrade alem de volume)

Revision ID: b56bb69a0ab0
Revises: b1582a0aeacc
Create Date: 2026-09-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b56bb69a0ab0'
down_revision: Union[str, Sequence[str], None] = 'b1582a0aeacc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('plano', sa.Column('permite_ab_teste_cadencia', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('plano', sa.Column('permite_auto_aprovacao', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('plano', sa.Column('permite_webhook_relatorio', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('plano', sa.Column('permite_api_parceiros', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('plano', sa.Column('permite_subtenants', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('plano', sa.Column('retencao_dias_relatorio', sa.Integer(), nullable=True))
    op.add_column('plano', sa.Column('retencao_dias_auditoria', sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('plano', 'retencao_dias_auditoria')
    op.drop_column('plano', 'retencao_dias_relatorio')
    op.drop_column('plano', 'permite_subtenants')
    op.drop_column('plano', 'permite_api_parceiros')
    op.drop_column('plano', 'permite_webhook_relatorio')
    op.drop_column('plano', 'permite_auto_aprovacao')
    op.drop_column('plano', 'permite_ab_teste_cadencia')
