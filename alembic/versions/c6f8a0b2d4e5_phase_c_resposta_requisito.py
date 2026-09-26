"""Phase C: resposta do fornecedor por requisito (Enterprise Bids e apoio à proposta).

`resposta` em `requisito_licitacao` e no espelho `requisito_sourcing`.
ADD/DROP COLUMN direto (sem recriar tabela no SQLite: preserva o trigger de
lado imutável).

Revision ID: c6f8a0b2d4e5
Revises: b4e6f8a0c2d3
Create Date: 2026-09-26
"""

import sqlalchemy as sa

from alembic import op

revision = "c6f8a0b2d4e5"
down_revision = "b4e6f8a0c2d3"
branch_labels = None
depends_on = None

TABELAS = ("requisito_licitacao", "requisito_sourcing")


def upgrade() -> None:
    for tabela in TABELAS:
        op.add_column(tabela, sa.Column("resposta", sa.Text(), nullable=True))


def downgrade() -> None:
    for tabela in TABELAS:
        op.drop_column(tabela, "resposta")
