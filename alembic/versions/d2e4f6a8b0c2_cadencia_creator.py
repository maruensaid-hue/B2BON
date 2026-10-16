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
    with op.batch_alter_table("cadencia") as batch_op:
        batch_op.add_column(sa.Column("criado_por_usuario_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_cadencia_criado_por_usuario_id", ["criado_por_usuario_id"])
        batch_op.create_foreign_key(
            "fk_cadencia_criado_por_usuario_id_usuario",
            "usuario",
            ["criado_por_usuario_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("cadencia") as batch_op:
        batch_op.drop_constraint("fk_cadencia_criado_por_usuario_id_usuario", type_="foreignkey")
        batch_op.drop_index("ix_cadencia_criado_por_usuario_id")
        batch_op.drop_column("criado_por_usuario_id")
