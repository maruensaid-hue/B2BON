"""Plano Teste passa a permitir criar sub-tenants (revenda)

Raio-X 2026-09-24: Mauricio (admin no plano gratuito "Teste") reportou
nao conseguir criar um sub-tenant ("Vendedor" - rotulo customizado da
hierarquia dele pra "revendedor") abaixo do proprio tenant -- bloqueado
por app/api/v1/admin_tenants.py:63 (`permite_subtenants` do Plano),
igual ja bloqueava max_usuarios antes da correcao em 1e5087198fab.

Mesma logica daquela correcao: quem recebe o plano Teste pra avaliar a
plataforma precisa conseguir testar a hierarquia de revenda tambem, nao
so convidar vendedores para o proprio tenant. Nenhuma outra restricao
do plano muda (self-service continua bloqueado, limites de
enriquecimento/cadencia/campanha semanais/mensais continuam valendo).

Revision ID: 327c75fdadef
Revises: 807d7076f1df
Create Date: 2026-09-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '327c75fdadef'
down_revision: Union[str, Sequence[str], None] = '807d7076f1df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NOME_PLANO = "Teste"


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE plano SET permite_subtenants = 1 WHERE nome = :nome"), {"nome": NOME_PLANO})


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE plano SET permite_subtenants = 0 WHERE nome = :nome"), {"nome": NOME_PLANO})
