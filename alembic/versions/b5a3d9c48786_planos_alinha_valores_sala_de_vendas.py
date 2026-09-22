"""Plano - alinha Starter/Professional/Enterprise com a tabela comercial e adiciona limites de cadencia/campanha por mes

Raio-X 2026-09-22: a pagina publica de Planos e Valores (e o botao
"Assine aqui" que leva ao checkout) anuncia preco/numero de usuarios por
plano diferentes dos que estavam gravados aqui desde a Onda A (valores
provisorios, nunca decisao comercial fechada - ver docstring de
`Plano`). Sem esse ajuste, o cliente veria um preco na vitrine e pagaria
outro no Mercado Pago. "Teste" (convite gratuito) so ganha os novos
limites de cadencia/campanha aqui - usuarios ja ficou sem teto pra esse
plano na revisao anterior (1e5087198fab), intencional, nao mexido aqui.

Tambem adiciona `limite_cadencias_mes`/`limite_campanhas_mes` (mesmo
padrao nullable=sem-teto dos limites de enriquecimento semanal, so que
de ciclo mensal) - pedido do usuario pra restringir tambem por volume de
cadencia/campanha criada, nao so por usuarios/franquia/enriquecimento.
Valores calibrados como fracao da franquia mensal de cada plano (~10%
cadencias, ~5% campanhas), mesma logica ja documentada pros limites de
enriquecimento - ajustaveis depois via Admin -> Planos.

Revision ID: b5a3d9c48786
Revises: 1e5087198fab
Create Date: 2026-09-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b5a3d9c48786'
down_revision: Union[str, Sequence[str], None] = '1e5087198fab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


plano = sa.table(
    'plano',
    sa.column('nome', sa.String),
    sa.column('max_usuarios', sa.Integer),
    sa.column('preco_mensal', sa.Float),
    sa.column('limite_cadencias_mes', sa.Integer),
    sa.column('limite_campanhas_mes', sa.Integer),
)


def upgrade() -> None:
    op.add_column('plano', sa.Column('limite_cadencias_mes', sa.Integer(), nullable=True))
    op.add_column('plano', sa.Column('limite_campanhas_mes', sa.Integer(), nullable=True))

    op.execute(plano.update().where(plano.c.nome == 'POC').values(
        limite_cadencias_mes=5, limite_campanhas_mes=2,
    ))
    op.execute(plano.update().where(plano.c.nome == 'Teste').values(
        limite_cadencias_mes=20, limite_campanhas_mes=10,
    ))
    op.execute(plano.update().where(plano.c.nome == 'Starter').values(
        max_usuarios=5, preco_mensal=924.50, limite_cadencias_mes=20, limite_campanhas_mes=10,
    ))
    op.execute(plano.update().where(plano.c.nome == 'Professional').values(
        max_usuarios=10, preco_mensal=1664.10, limite_cadencias_mes=80, limite_campanhas_mes=40,
    ))
    op.execute(plano.update().where(plano.c.nome == 'Enterprise').values(
        max_usuarios=20, preco_mensal=2958.40, limite_cadencias_mes=500, limite_campanhas_mes=250,
    ))


def downgrade() -> None:
    op.execute(plano.update().where(plano.c.nome == 'Starter').values(max_usuarios=10, preco_mensal=490.0))
    op.execute(plano.update().where(plano.c.nome == 'Professional').values(max_usuarios=25, preco_mensal=990.0))
    op.execute(plano.update().where(plano.c.nome == 'Enterprise').values(max_usuarios=999, preco_mensal=2490.0))

    op.drop_column('plano', 'limite_campanhas_mes')
    op.drop_column('plano', 'limite_cadencias_mes')
