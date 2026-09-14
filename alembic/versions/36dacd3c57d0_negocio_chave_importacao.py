"""Negocio.chave_importacao - idempotencia de import/export de CSV

Revision ID: 36dacd3c57d0
Revises: 11abe6daa98d
Create Date: 2026-09-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '36dacd3c57d0'
down_revision: Union[str, Sequence[str], None] = '11abe6daa98d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('negocio', sa.Column('chave_importacao', sa.String(), nullable=True))
    # Só um negócio por chave de importação dentro do tenant — garantido no
    # banco (índice único parcial), não por checagem prévia em código.
    # Reimportar o mesmo CSV com a mesma chave atualiza em vez de duplicar.
    op.create_index(
        'ix_negocio_chave_importacao_unica',
        'negocio',
        ['tenant_id', 'chave_importacao'],
        unique=True,
        postgresql_where=sa.text('chave_importacao IS NOT NULL'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_negocio_chave_importacao_unica', table_name='negocio')
    op.drop_column('negocio', 'chave_importacao')
