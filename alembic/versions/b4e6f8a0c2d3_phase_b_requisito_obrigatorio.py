"""Phase B: obrigatoriedade do requisito (plano unificado §18).

`obrigatorio` em `requisito_licitacao` e `requisito_sourcing` (espelho).
Nulo = UNKNOWN: linhas anteriores ficam assim até nova análise (nada é
inferido retroativamente pela migração). Nos achados do comprador (JSON),
a chave `obrigatorio` entra nas análises novas.

Revision ID: b4e6f8a0c2d3
Revises: a3d5f7b9c1e2
Create Date: 2026-09-26
"""

import sqlalchemy as sa

from alembic import op

revision = "b4e6f8a0c2d3"
down_revision = "a3d5f7b9c1e2"
branch_labels = None
depends_on = None

TABELAS = ("requisito_licitacao", "requisito_sourcing")


# ADD/DROP COLUMN direto (SQLite ≥ 3.35 e Postgres): sem `batch_alter_table`, que no
# SQLite recria a tabela e perderia o trigger de lado imutável de `requisito_sourcing`.
def upgrade() -> None:
    for tabela in TABELAS:
        op.add_column(tabela, sa.Column("obrigatorio", sa.Boolean(), nullable=True))


def downgrade() -> None:
    for tabela in TABELAS:
        op.drop_column(tabela, "obrigatorio")
