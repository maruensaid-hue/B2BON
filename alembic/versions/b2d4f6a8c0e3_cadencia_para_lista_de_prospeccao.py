"""Cadência para lista de prospecção: cadencia.lista_prospeccao_id.

Listas de prospecção (como a "Importação LinkedIn") não têm ICP; até aqui a cadência só podia ser criada e gerada com um ICP. A coluna liga a cadência a uma
lista; a geração fica restrita às empresas dela. Nullable: as cadências existentes continuam como estavam.

Downgrade: remove o índice e a coluna.

Revision ID: b2d4f6a8c0e3
Revises: a1c3e5b7d9f1
Create Date: 2026-10-23
"""
import sqlalchemy as sa
from alembic import op

revision = "b2d4f6a8c0e3"
down_revision = "a1c3e5b7d9f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("cadencia") as lote:
        lote.add_column(sa.Column("lista_prospeccao_id", sa.Integer(), nullable=True))
        lote.create_foreign_key("fk_cadencia_lista_prospeccao", "lista_prospeccao", ["lista_prospeccao_id"], ["id"])
        lote.create_index("ix_cadencia_lista_prospeccao_id", ["lista_prospeccao_id"])


def downgrade() -> None:
    with op.batch_alter_table("cadencia") as lote:
        lote.drop_index("ix_cadencia_lista_prospeccao_id")
        lote.drop_constraint("fk_cadencia_lista_prospeccao", type_="foreignkey")
        lote.drop_column("lista_prospeccao_id")
