"""Cache persistido da Central de Negocios (mercado/cambio)

Raio-X 2026-09-24: bug real reportado pelo usuario - a janela de
cambio ficava "indisponivel" pra sempre depois de um cold start do
plano free do Render (cache em memoria de `central_negocios_service`
zerado) coincidindo com a AwesomeAPI devolvendo 429. Essa tabela
persiste o ultimo valor bom conhecido, sobrevivendo a restart.

Revision ID: d2e3f4a5b6c7
Revises: 807d7076f1df
Create Date: 2026-09-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d2e3f4a5b6c7"
down_revision: Union[str, None] = "807d7076f1df"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cache_mercado_externo",
        sa.Column("chave", sa.String(), nullable=False),
        sa.Column("valor", sa.JSON(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("chave"),
    )


def downgrade() -> None:
    op.drop_table("cache_mercado_externo")
