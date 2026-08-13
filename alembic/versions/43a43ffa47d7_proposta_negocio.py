"""proposta_negocio

Revision ID: 43a43ffa47d7
Revises: 323888d912ac
Create Date: 2026-08-13
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "43a43ffa47d7"
down_revision: str | Sequence[str] | None = "323888d912ac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "proposta_negocio",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocio.id"), nullable=False),
        sa.Column("versao", sa.Integer(), nullable=False),
        sa.Column("nome_arquivo", sa.String(), nullable=False),
        sa.Column("tipo_mime", sa.String(), nullable=False),
        sa.Column("conteudo", sa.LargeBinary(), nullable=False),
        sa.Column("tamanho_bytes", sa.Integer(), nullable=False),
        sa.Column("gerada_automaticamente", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("enviada_por_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_proposta_negocio_tenant_id", "proposta_negocio", ["tenant_id"])
    op.create_index("ix_proposta_negocio_negocio_id", "proposta_negocio", ["negocio_id"])


def downgrade() -> None:
    op.drop_index("ix_proposta_negocio_negocio_id", table_name="proposta_negocio")
    op.drop_index("ix_proposta_negocio_tenant_id", table_name="proposta_negocio")
    op.drop_table("proposta_negocio")
