"""Lista de bloqueio de contatos (bloqueio_contato).

E-mail e/ou telefone de quem pediu para não receber mais nada, valendo para todas as campanhas da empresa. Tabela nova: nada do que já existe muda.

Downgrade: remove a tabela.

Revision ID: d4f6a8c0e2b4
Revises: c1e3a5b7d9f4
Create Date: 2026-10-28
"""
import sqlalchemy as sa
from alembic import op

revision = "d4f6a8c0e2b4"
down_revision = "c1e3a5b7d9f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bloqueio_contato",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("telefone", sa.String(), nullable=True),
        sa.Column("motivo", sa.String(), nullable=False),
        sa.Column("origem", sa.String(), nullable=False),
        sa.Column("criado_por", sa.String(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_bloqueio_contato_tenant_id", "bloqueio_contato", ["tenant_id"])
    op.create_index("ix_bloqueio_contato_email", "bloqueio_contato", ["email"])


def downgrade() -> None:
    op.drop_index("ix_bloqueio_contato_email", table_name="bloqueio_contato")
    op.drop_index("ix_bloqueio_contato_tenant_id", table_name="bloqueio_contato")
    op.drop_table("bloqueio_contato")
