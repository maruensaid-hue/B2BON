"""Campanha: empresa do destinatário (campanha_destinatario.empresa).

Destinatário de lista colada não tem cadastro de empresa por trás, então o `[Empresa]` do e-mail não tinha de onde sair; a lista colada passa a aceitar a
coluna "Empresa" e o contato vindo do CRM guarda o nome da empresa no momento em que entra na campanha. Nullable: os destinatários existentes continuam
como estavam (o envio ainda consulta o cadastro quando o campo está vazio).

Downgrade: remove a coluna.

Revision ID: f6b8d0e2a4c7
Revises: e5a7c9d1f3b6
Create Date: 2026-10-27
"""
import sqlalchemy as sa
from alembic import op

revision = "f6b8d0e2a4c7"
down_revision = "e5a7c9d1f3b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Acrescenta `campanha_destinatario.empresa`."""
    with op.batch_alter_table("campanha_destinatario") as lote:
        lote.add_column(sa.Column("empresa", sa.String(), nullable=True))


def downgrade() -> None:
    """Remove a coluna `campanha_destinatario.empresa`."""
    with op.batch_alter_table("campanha_destinatario") as lote:
        lote.drop_column("empresa")
