"""Convite gratuito (ConviteVitrine.gratuito) e visibilidade de plano no self-service

Revision ID: 8dc3e8c6e767
Revises: ae2598da5f96
Create Date: 2026-08-21 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8dc3e8c6e767'
down_revision: Union[str, Sequence[str], None] = 'ae2598da5f96'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOME_PLANO_TESTE = "Teste"


def upgrade() -> None:
    op.add_column(
        'plano',
        sa.Column('visivel_self_service', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        'convite_vitrine',
        sa.Column('gratuito', sa.Boolean(), nullable=False, server_default=sa.false()),
    )

    conn = op.get_bind()
    conn.execute(
        sa.text("UPDATE plano SET visivel_self_service = false WHERE nome = :nome"),
        {"nome": NOME_PLANO_TESTE},
    )


def downgrade() -> None:
    op.drop_column('convite_vitrine', 'gratuito')
    op.drop_column('plano', 'visivel_self_service')
