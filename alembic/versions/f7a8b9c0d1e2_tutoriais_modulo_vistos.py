"""Usuario.tutoriais_modulo_vistos - tutorial por modulo, coexiste com o tour grande

Raio-X 2026-09-21: cada modulo (CRM, Prospeccao, ...) ganha um tutorial
proprio disparado na primeira visita. Lista de chaves de modulo ja
vistas, mesmo molde de `preferencias_dashboard` (JSON list, nullable,
sem backfill - nulo/vazio ja significa "nenhum modulo visto ainda").

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-09-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f7a8b9c0d1e2'
down_revision: Union[str, Sequence[str], None] = 'e6f7a8b9c0d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('usuario', sa.Column('tutoriais_modulo_vistos', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('usuario', 'tutoriais_modulo_vistos')
