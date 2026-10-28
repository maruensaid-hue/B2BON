"""Campanha: reserva do disparo (campanha.processando_ate).

O envio de uma campanha agora começa logo após "Marcar como pronta" (em segundo plano) e continua pelo agendador; a reserva impede que os dois enviem a
mesma campanha ao mesmo tempo e vence sozinha se o processo cair no meio. Nullable: as campanhas existentes continuam como estavam.

Downgrade: remove a coluna.

Revision ID: e5a7c9d1f3b6
Revises: d4f6b8c0e2a5
Create Date: 2026-10-26
"""
import sqlalchemy as sa
from alembic import op

revision = "e5a7c9d1f3b6"
down_revision = "d4f6b8c0e2a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Acrescenta `campanha.processando_ate` (a reserva do disparo)."""
    with op.batch_alter_table("campanha") as lote:
        lote.add_column(sa.Column("processando_ate", sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Remove a coluna `campanha.processando_ate`."""
    with op.batch_alter_table("campanha") as lote:
        lote.drop_column("processando_ate")
