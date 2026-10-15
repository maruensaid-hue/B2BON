"""Merge security ownership migration with existing MAP quota migration.

Revision ID: c8d0e2f4a6b8
Revises: f3b5d7f9a1c4, f7a1c9e3b5d7
Create Date: 2026-10-15
"""
from alembic import op

revision = "c8d0e2f4a6b8"
down_revision = ("f3b5d7f9a1c4", "f7a1c9e3b5d7")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Merge-only revision: both parent migrations have already applied their schema changes.
    pass


def downgrade() -> None:
    # Merge-only revision: downgrade traverses the two parent revisions separately.
    pass
