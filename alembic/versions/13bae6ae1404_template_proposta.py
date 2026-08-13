"""template_proposta

Revision ID: 13bae6ae1404
Revises: 43a43ffa47d7
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "13bae6ae1404"
down_revision: str | Sequence[str] | None = "43a43ffa47d7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "template_proposta",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("texto_introdutorio", sa.Text(), nullable=True),
        sa.Column("logo_conteudo", sa.LargeBinary(), nullable=True),
        sa.Column("logo_tipo_mime", sa.String(), nullable=True),
        sa.Column("termo_aceite", sa.Text(), nullable=True),
        sa.Column("mostrar_tabela_produtos", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("mostrar_tabela_servicos", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("atualizado_em", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_template_proposta_tenant_id", "template_proposta", ["tenant_id"], unique=True)

    op.create_table(
        "item_template_proposta",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("template_id", sa.Integer(), sa.ForeignKey("template_proposta.id"), nullable=False),
        sa.Column("tipo", sa.String(), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("descricao", sa.String(), nullable=False),
        sa.Column("valor", sa.Float(), nullable=True),
    )
    op.create_index("ix_item_template_proposta_tenant_id", "item_template_proposta", ["tenant_id"])
    op.create_index("ix_item_template_proposta_template_id", "item_template_proposta", ["template_id"])


def downgrade() -> None:
    op.drop_index("ix_item_template_proposta_template_id", table_name="item_template_proposta")
    op.drop_index("ix_item_template_proposta_tenant_id", table_name="item_template_proposta")
    op.drop_table("item_template_proposta")
    op.drop_index("ix_template_proposta_tenant_id", table_name="template_proposta")
    op.drop_table("template_proposta")
