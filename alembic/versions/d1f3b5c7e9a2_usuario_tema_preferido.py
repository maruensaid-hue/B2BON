"""D-086: tema da interface (claro/escuro) como preferência do usuário.

- `usuario.tema_preferido`: "light" | "dark"; nulo = padrão (claro). Preferência individual — não do tenant.

Revision ID: d1f3b5c7e9a2
Revises: c0e2a4b6d8f1
Create Date: 2026-10-04
"""

import sqlalchemy as sa

from alembic import op

revision = "d1f3b5c7e9a2"
down_revision = "c0e2a4b6d8f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("usuario") as tabela:
        tabela.add_column(sa.Column("tema_preferido", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("usuario") as tabela:
        tabela.drop_column("tema_preferido")
