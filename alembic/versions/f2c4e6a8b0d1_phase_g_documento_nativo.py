"""Phase G: documento de especificação do comprador privado no modelo unificado.

`documento_sourcing` recebe o texto por página (para ancorar a extração da IA)
e o arquivo, ambos opcionais: os documentos espelhados de Bids e Procurement
continuam só com os metadados. Colunas adicionadas direto (sem recriar a
tabela), para manter o trigger de lado imutável da S3 no SQLite.

Revision ID: f2c4e6a8b0d1
Revises: e1b3d5f7a9c0
Create Date: 2026-09-26
"""

import sqlalchemy as sa

from alembic import op

revision = "f2c4e6a8b0d1"
down_revision = "e1b3d5f7a9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documento_sourcing", sa.Column("paginas_texto", sa.JSON(), nullable=True))
    op.add_column("documento_sourcing", sa.Column("conteudo", sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    op.drop_column("documento_sourcing", "conteudo")
    op.drop_column("documento_sourcing", "paginas_texto")
