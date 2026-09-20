"""Anexo de foto/video em post da Rede Social - midia_* em post_rede_social

Revision ID: f1a2b3c4d5e6
Revises: e7f8a9b0c1d2
Create Date: 2026-09-20

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, Sequence[str], None] = 'e7f8a9b0c1d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('post_rede_social', sa.Column('midia_conteudo', sa.LargeBinary(), nullable=True))
    op.add_column('post_rede_social', sa.Column('midia_tipo_mime', sa.String(), nullable=True))
    op.add_column('post_rede_social', sa.Column('midia_tamanho_bytes', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('post_rede_social', 'midia_tamanho_bytes')
    op.drop_column('post_rede_social', 'midia_tipo_mime')
    op.drop_column('post_rede_social', 'midia_conteudo')
