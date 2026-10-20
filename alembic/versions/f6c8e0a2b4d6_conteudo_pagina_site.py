"""Conteúdo das páginas coletadas do site institucional de cada conta.

Revision ID: f6c8e0a2b4d6
Revises: e5b7d9f1a3c5
Create Date: 2026-10-20
"""
from alembic import op
import sqlalchemy as sa

revision = "f6c8e0a2b4d6"
down_revision = "e5b7d9f1a3c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conteudo_pagina_site",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("conta_id", sa.Integer(), sa.ForeignKey("conta.id"), nullable=False),
        sa.Column("url", sa.String(), nullable=False),
        sa.Column("conteudo", sa.Text(), nullable=False),
        sa.Column("coletado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("conta_id", "url", name="uq_conteudo_pagina_site_conta_url"),
    )
    op.create_index("ix_conteudo_pagina_site_tenant_id", "conteudo_pagina_site", ["tenant_id"])
    op.create_index("ix_conteudo_pagina_site_conta_id", "conteudo_pagina_site", ["conta_id"])


def downgrade() -> None:
    op.drop_index("ix_conteudo_pagina_site_conta_id", table_name="conteudo_pagina_site")
    op.drop_index("ix_conteudo_pagina_site_tenant_id", table_name="conteudo_pagina_site")
    op.drop_table("conteudo_pagina_site")
