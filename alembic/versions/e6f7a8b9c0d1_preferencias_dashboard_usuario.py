"""Usuario.preferencias_dashboard - dashboard customizavel por usuario

Redesign Salesforce (raio-X 2026-09-21), sub-entrega D: ordem/visibilidade
das 3 secoes da Dashboard (grade de KPIs, funil, economia), reordenavel e
ocultavel por usuario. `null` = nunca customizou, cai no default calculado
em `panel_service.obter_preferencias_dashboard` (nao precisa de backfill).

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-09-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e6f7a8b9c0d1'
down_revision: Union[str, Sequence[str], None] = 'd5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('usuario', sa.Column('preferencias_dashboard', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('usuario', 'preferencias_dashboard')
