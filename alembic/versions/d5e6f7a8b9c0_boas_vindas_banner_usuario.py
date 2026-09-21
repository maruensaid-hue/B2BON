"""Usuario.boas_vindas_banner_dispensado - banner de boas-vindas da Dashboard

Redesign Salesforce (raio-X 2026-09-21), sub-entrega C: banner de atalhos
na Dashboard, dispensável em definitivo por usuário. Backfill `True` pra
todo mundo já cadastrado — sem isso, quem já conhece a plataforma veria o
banner reaparecer uma vez após o deploy. Só usuários criados depois desta
migração nascem com `False`.

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-09-21

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, Sequence[str], None] = 'c4d5e6f7a8b9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'usuario',
        sa.Column('boas_vindas_banner_dispensado', sa.Boolean(), server_default='false', nullable=False),
    )
    op.execute("UPDATE usuario SET boas_vindas_banner_dispensado = true")


def downgrade() -> None:
    op.drop_column('usuario', 'boas_vindas_banner_dispensado')
