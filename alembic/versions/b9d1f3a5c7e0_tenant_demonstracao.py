"""D-082: ambiente de demonstração — tenant efêmero com dados fictícios.

- `tenant.demo_expira_em`: nulo = tenant real; preenchido = tenant de demonstração, apagado depois de expirar.

Revision ID: b9d1f3a5c7e0
Revises: a8c0e2f4b6d9
Create Date: 2026-10-01
"""

import sqlalchemy as sa

from alembic import op

revision = "b9d1f3a5c7e0"
down_revision = "a8c0e2f4b6d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tenant") as tabela:
        tabela.add_column(sa.Column("demo_expira_em", sa.DateTime(), nullable=True))
        tabela.create_index("ix_tenant_demo_expira_em", ["demo_expira_em"])


def downgrade() -> None:
    with op.batch_alter_table("tenant") as tabela:
        tabela.drop_index("ix_tenant_demo_expira_em")
        tabela.drop_column("demo_expira_em")
