"""Pre-reserva: indices das chaves estrangeiras (conta, decisor, negocio).

Regra da Fase 17 (`tests/unit/test_indices_fk.py`): toda FK tem indice. Sem eles, o join por conta/negocio e o ON DELETE de uma conta varrem a tabela
inteira. So cria indices; nenhum dado muda.

Revision ID: f6b8d0a2c4e1
Revises: e5a7c9b1d3f2
Create Date: 2026-11-12
"""
from alembic import op

revision = "f6b8d0a2c4e1"
down_revision = "e5a7c9b1d3f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_pre_reserva_conta_id", "pre_reserva", ["conta_id"])
    op.create_index("ix_pre_reserva_decisor_id", "pre_reserva", ["decisor_id"])
    op.create_index("ix_pre_reserva_negocio_id", "pre_reserva", ["negocio_id"])


def downgrade() -> None:
    op.drop_index("ix_pre_reserva_negocio_id", table_name="pre_reserva")
    op.drop_index("ix_pre_reserva_decisor_id", table_name="pre_reserva")
    op.drop_index("ix_pre_reserva_conta_id", table_name="pre_reserva")
