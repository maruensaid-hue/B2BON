"""POC: até 3 pesquisas de decisores no total (1 decisor por empresa).

O PO definiu que o cliente em POC pode fazer até 3 pesquisas, com 1 decisor por empresa. A linha do plano POC (`modo=poc_autorizada`, 1 decisor) criada pela
matriz ganha `limite_pesquisas_periodo = 3`; a autorização da POC (`periodicidade=unica`) conta essas pesquisas na vida do tenant. Só atualiza a linha que
ainda está como a matriz a deixou (sem limite de pesquisas) e foi aprovada pelo PO.

Downgrade: volta o limite para nulo nessas linhas.

Revision ID: f9b1d3e5a7c9
Revises: e8a0c2d4f6b8
Create Date: 2026-10-22
"""
import sqlalchemy as sa
from alembic import op

revision = "f9b1d3e5a7c9"
down_revision = "e8a0c2d4f6b8"
branch_labels = None
depends_on = None

_APROVADOR = "po:matriz-2026-10-21"


def upgrade() -> None:
    op.execute(sa.text(
        "UPDATE enriquecimento_config_plano SET limite_pesquisas_periodo = 3 "
        "WHERE modo = 'poc_autorizada' AND plano_id IS NOT NULL AND limite_pesquisas_periodo IS NULL AND valido_ate IS NULL AND aprovado_por = :aprovador"
    ).bindparams(aprovador=_APROVADOR))


def downgrade() -> None:
    op.execute(sa.text(
        "UPDATE enriquecimento_config_plano SET limite_pesquisas_periodo = NULL "
        "WHERE modo = 'poc_autorizada' AND plano_id IS NOT NULL AND limite_pesquisas_periodo = 3 AND aprovado_por = :aprovador"
    ).bindparams(aprovador=_APROVADOR))
