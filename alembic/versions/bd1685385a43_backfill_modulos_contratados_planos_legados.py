"""Backfill de modulos_contratados pra planos que nao eram nenhum dos 5 nomeados

Raio-X 2026-09-24 (achado via falha de E2E no CI): a migracao
807d7076f1df adicionou `modulos_contratados` com `server_default='[]'`
e so preencheu explicitamente os 5 planos de suite conhecidos por nome
(POC/Teste/Starter/Professional/Enterprise) + os 9 avulsos novos.
Qualquer OUTRO `Plano` ja existente (ex.: um plano customizado criado
via Admin -> Planos antes dessa migracao, ou o "E2E Teste" do seed de
teste) ficou silenciosamente com `modulos_contratados=[]` -- ZERO
modulos liberados, revogando acesso a CRM/MAP/PREDATOR de quem estava
nesse plano, mesmo sem nenhuma mudanca comercial pretendida.

Esta migracao corrige o efeito colateral: qualquer `Plano` que ainda
esteja com a lista vazia (nunca foi explicitamente classificado como
avulso de 1 modulo) volta a liberar os tres modulos, preservando o
comportamento de antes desta feature (todo mundo com licenca ativa
tinha acesso total). Planos avulsos de verdade (modulos_contratados
com exatamente 1 item) nao sao tocados.

Revision ID: bd1685385a43
Revises: 327c75fdadef
Create Date: 2026-09-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bd1685385a43'
down_revision: Union[str, Sequence[str], None] = '327c75fdadef'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


plano = sa.table(
    'plano',
    sa.column('id', sa.Integer),
    sa.column('modulos_contratados', sa.JSON),
)


def upgrade() -> None:
    conn = op.get_bind()
    linhas = conn.execute(sa.select(plano.c.id, plano.c.modulos_contratados)).fetchall()
    for linha in linhas:
        if not linha.modulos_contratados:
            conn.execute(
                plano.update().where(plano.c.id == linha.id).values(
                    modulos_contratados=["map", "predator", "crm"],
                )
            )


def downgrade() -> None:
    # Irreversível de propósito: não temos como distinguir, depois do
    # fato, um plano que ficou vazio por engano (o bug que esta migração
    # corrige) de um plano que alguém tenha zerado de propósito depois
    # dela. Reverter aqui arriscaria reintroduzir o próprio bug.
    pass
