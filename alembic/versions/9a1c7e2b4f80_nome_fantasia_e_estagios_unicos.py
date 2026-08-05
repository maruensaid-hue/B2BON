"""nome_fantasia na conta e unicidade de estagio_funil

Revision ID: 9a1c7e2b4f80
Revises: 741eed234a25
Create Date: 2026-08-05 20:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9a1c7e2b4f80'
down_revision: Union[str, Sequence[str], None] = '741eed234a25'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('conta', sa.Column('nome_fantasia', sa.String(), nullable=True))

    # Dedup defensivo antes de criar a constraint única: bug real de
    # producao (garantir_estagios_padrao sem lock -- corrigido no
    # servico) deixou pares duplicados de (tenant_id, ordem). Mantem a
    # linha de menor id, reaponta negocio.estagio_id que apontava pra
    # duplicata, e apaga as duplicatas -- sem isso a UniqueConstraint
    # abaixo falharia no ambiente que ja tem os dados repetidos.
    conn = op.get_bind()
    conn.execute(sa.text(
        """
        WITH duplicadas AS (
            SELECT id, tenant_id, ordem,
                   MIN(id) OVER (PARTITION BY tenant_id, ordem) AS id_canonico
            FROM estagio_funil
        )
        UPDATE negocio
        SET estagio_id = duplicadas.id_canonico
        FROM duplicadas
        WHERE negocio.estagio_id = duplicadas.id
          AND duplicadas.id != duplicadas.id_canonico
        """
    ))
    conn.execute(sa.text(
        """
        DELETE FROM estagio_funil
        WHERE id NOT IN (
            SELECT MIN(id) FROM estagio_funil GROUP BY tenant_id, ordem
        )
        """
    ))

    op.create_unique_constraint(
        'uq_estagio_funil_tenant_ordem', 'estagio_funil', ['tenant_id', 'ordem']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_estagio_funil_tenant_ordem', 'estagio_funil', type_='unique')
    op.drop_column('conta', 'nome_fantasia')
