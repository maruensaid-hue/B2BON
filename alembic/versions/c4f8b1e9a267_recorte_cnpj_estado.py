"""Estado do recorte de CNPJ carregado automaticamente via cron

Revision ID: c4f8b1e9a267
Revises: a1c9d5e73f21
Create Date: 2026-08-20 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4f8b1e9a267'
down_revision: Union[str, Sequence[str], None] = 'a1c9d5e73f21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'recorte_cnpj_estado',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('mes_competencia', sa.String(), nullable=False),
        sa.Column('cnae_codigos_cobertos', sa.JSON(), nullable=False),
        sa.Column('ufs_cobertos', sa.JSON(), nullable=False),
        sa.Column('atualizado_em', sa.DateTime(), server_default=sa.func.now()),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('recorte_cnpj_estado')
