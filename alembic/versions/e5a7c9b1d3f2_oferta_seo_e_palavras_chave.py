"""Oferta: SEO (título e descrição) e palavras-chave, usados na composição das mensagens.

Três colunas novas, todas opcionais e sem valor padrão: oferta existente continua igual e o prompt das mensagens só ganha o trecho quando o campo é preenchido.

Revision ID: e5a7c9b1d3f2
Revises: c7e9a1b3d5f7
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = "e5a7c9b1d3f2"
down_revision = "c7e9a1b3d5f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("oferta", sa.Column("palavras_chave", sa.JSON(), nullable=True))
    op.add_column("oferta", sa.Column("seo_titulo", sa.String(), nullable=True))
    op.add_column("oferta", sa.Column("seo_descricao", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("oferta", "seo_descricao")
    op.drop_column("oferta", "seo_titulo")
    op.drop_column("oferta", "palavras_chave")
