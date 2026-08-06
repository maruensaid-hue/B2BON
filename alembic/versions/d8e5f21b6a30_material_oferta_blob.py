"""Material de oferta: blob no banco em vez de path em disco (raio-X)

Revision ID: d8e5f21b6a30
Revises: c7d4e91a5f13
Create Date: 2026-08-06 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd8e5f21b6a30'
down_revision: Union[str, Sequence[str], None] = 'c7d4e91a5f13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('material_oferta', sa.Column('conteudo', sa.LargeBinary(), nullable=True))
    # O disco do Render é efêmero — qualquer linha existente já aponta pra
    # um arquivo que não existe mais, então não há conteúdo real pra
    # migrar. Backfill com vazio só para permitir o NOT NULL a seguir.
    op.execute("UPDATE material_oferta SET conteudo = '' WHERE conteudo IS NULL")
    with op.batch_alter_table('material_oferta') as batch_op:
        batch_op.alter_column('conteudo', existing_type=sa.LargeBinary(), nullable=False)
        batch_op.drop_column('caminho')


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('material_oferta') as batch_op:
        batch_op.add_column(sa.Column('caminho', sa.String(), nullable=True))
    op.execute("UPDATE material_oferta SET caminho = ''")
    with op.batch_alter_table('material_oferta') as batch_op:
        batch_op.alter_column('caminho', existing_type=sa.String(), nullable=False)
        batch_op.drop_column('conteudo')
