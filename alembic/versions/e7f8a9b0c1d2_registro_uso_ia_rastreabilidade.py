"""AI Audit - rastreabilidade real em RegistroUsoIa - Fase 0.5-C (master prompt secao 73)

Revision ID: e7f8a9b0c1d2
Revises: d6e7f8a9b0c1
Create Date: 2026-09-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e7f8a9b0c1d2'
down_revision: Union[str, Sequence[str], None] = 'd6e7f8a9b0c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('registro_uso_ia', sa.Column('model', sa.String(), nullable=True))
    op.add_column('registro_uso_ia', sa.Column('entidade_tipo', sa.String(), nullable=True))
    op.add_column('registro_uso_ia', sa.Column('entidade_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('registro_uso_ia', 'entidade_id')
    op.drop_column('registro_uso_ia', 'entidade_tipo')
    op.drop_column('registro_uso_ia', 'model')
