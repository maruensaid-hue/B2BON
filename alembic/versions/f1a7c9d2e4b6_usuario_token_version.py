"""Add per-user JWT version for session revocation.

Revision ID: f1a7c9d2e4b6
Revises: e2a4c6e8f0b3
Create Date: 2026-10-15
"""
from alembic import op
import sqlalchemy as sa

revision = "f1a7c9d2e4b6"
down_revision = "e2a4c6e8f0b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "usuario",
        sa.Column("token_version", sa.Integer(), server_default="0", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("usuario", "token_version")
