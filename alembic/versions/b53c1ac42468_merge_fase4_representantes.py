"""Merge das heads: fundacao de inteligencia (Fase 4) + representantes/captura de lead

Os dois ramos nasceram de bd1685385a43 em paralelo e podem ja estar
aplicados em ambientes diferentes (staging recebe os dois) - por isso um
merge sem operacoes em vez de reescrever o down_revision de um deles
(D-012).

Revision ID: b53c1ac42468
Revises: af4fcaf0098f, ef93ae5bea74
Create Date: 2026-09-25

"""
from typing import Sequence, Union


revision: str = 'b53c1ac42468'
down_revision: Union[str, Sequence[str], None] = ('af4fcaf0098f', 'ef93ae5bea74')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
