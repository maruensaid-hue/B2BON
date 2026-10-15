"""Track cadence creator for seller-scoped access.

Revision ID: d2e4f6a8b0c2
Revises: c8d0e2f4a6b8
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa

revision = "d2e4f6a8b0c2"
down_revision = "c8d0e2f4a6b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "cadencia",
        sa.Column("criado_por_usuario_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_cadencia_criado_por_usuario_id",
        "cadencia",
        ["criado_por_usuario_id"],
    )
    op.create_foreign_key(
        "fk_cadencia_criado_por_usuario_id_usuario",
        "cadencia",
        "usuario",
        ["criado_por_usuario_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_cadencia_criado_por_usuario_id_usuario", "cadencia", type_="foreignkey"
    )
    op.drop_index("ix_cadencia_criado_por_usuario_id", table_name="cadencia")
    op.drop_column("cadencia", "criado_por_usuario_id")
