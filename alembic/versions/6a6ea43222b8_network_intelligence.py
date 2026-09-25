"""Network Intelligence - Fase 8 do Master Prompt v4

Sinal de oportunidade guarda o negocio gerado e o destino da conversao
(crm | predator), para que sinais diferentes da mesma empresa nunca gerem
conta ou negocio duplicado.

Revision ID: 6a6ea43222b8
Revises: 7dc1428d524f
Create Date: 2026-09-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '6a6ea43222b8'
down_revision: Union[str, Sequence[str], None] = '7dc1428d524f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("sinal_oportunidade") as batch:
        batch.add_column(sa.Column("negocio_id_gerado", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("destino_conversao", sa.String(), nullable=True))
        batch.create_foreign_key("fk_sinal_negocio_gerado", "negocio", ["negocio_id_gerado"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("sinal_oportunidade") as batch:
        batch.drop_constraint("fk_sinal_negocio_gerado", type_="foreignkey")
        batch.drop_column("destino_conversao")
        batch.drop_column("negocio_id_gerado")
