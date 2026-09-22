"""max_usuarios nulo = sem limite; plano Teste passa a ser ilimitado

Revision ID: 1e5087198fab
Revises: f7a8b9c0d1e2
Create Date: 2026-09-22 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1e5087198fab'
down_revision: Union[str, Sequence[str], None] = 'f7a8b9c0d1e2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOME_PLANO = "Teste"
LIMITE_ANTERIOR = 10


def upgrade() -> None:
    """`max_usuarios` vira nullable, mesmo padrão já usado nesta tabela
    pra `limite_enriquecimento_*_semanal`/`retencao_dias_*` (nulo = sem
    limite). O plano "Teste" — free, só concedível por convite — passa a
    ter `max_usuarios=NULL`: admin gratuito pode convidar quantos
    vendedores precisar, sem tocar nenhuma outra restrição do plano
    (self-service continua bloqueado, limites de enriquecimento
    semanais continuam valendo, sem sub-tenants)."""
    with op.batch_alter_table('plano') as batch_op:
        batch_op.alter_column('max_usuarios', existing_type=sa.Integer(), nullable=True)
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE plano SET max_usuarios = NULL WHERE nome = :nome"), {"nome": NOME_PLANO})


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("UPDATE plano SET max_usuarios = :limite WHERE nome = :nome"),
        {"limite": LIMITE_ANTERIOR, "nome": NOME_PLANO},
    )
    with op.batch_alter_table('plano') as batch_op:
        batch_op.alter_column('max_usuarios', existing_type=sa.Integer(), nullable=False)
