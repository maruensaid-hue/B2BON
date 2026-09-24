"""Contratacao avulsa por modulo (MAP/PREDATOR/CRM) - modulos_contratados + categoria em Plano, novos planos avulsos

Raio-X 2026-09-24: a pagina publica de Planos e Valores ja anunciava
contratacao avulsa por modulo, mas so como lead pro comercial - nao
existia em nenhuma camada do sistema o conceito de "tenant contratou so
um modulo". Em vez de permitir mais de uma Licenca por tenant (mudanca
grande, tocaria o fluxo de pagamento/webhook inteiro), a abordagem
adotada foi criar mais linhas de Plano (uma por modulo x faixa de
usuario), cada uma com seu proprio preco_mensal fixo - o checkout
continua sendo "escolher 1 Plano", sem mudar cardinalidade.

`modulos_contratados` (JSON, lista de "map"/"predator"/"crm") e o dado
que app/api/deps.py:exigir_modulo consulta via PlanLimitsProvider pra
decidir se libera ou barra (403) uma rota do MAP/PREDATOR/CRM.
`categoria` ("suite"/"modulo") so organiza a exibicao no picker de
checkout, sem nenhum papel na checagem de acesso.

Confirmado com o usuario: contratar PREDATOR avulso libera o pipeline
inteiro (nao um subconjunto de features) - por isso um unico modulo
"predator" cobre todos os routers do pipeline de prospeccao.

Revision ID: 807d7076f1df
Revises: c9d8e7f6a5b4
Create Date: 2026-09-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '807d7076f1df'
down_revision: Union[str, Sequence[str], None] = 'c9d8e7f6a5b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


plano = sa.table(
    'plano',
    sa.column('id', sa.Integer),
    sa.column('nome', sa.String),
    sa.column('franquia_contas_mes', sa.Integer),
    sa.column('max_usuarios', sa.Integer),
    sa.column('preco_mensal', sa.Float),
    sa.column('visivel_self_service', sa.Boolean),
    sa.column('limite_enriquecimento_site_semanal', sa.Integer),
    sa.column('limite_enriquecimento_contatos_semanal', sa.Integer),
    sa.column('limite_cadencias_mes', sa.Integer),
    sa.column('limite_campanhas_mes', sa.Integer),
    sa.column('permite_ab_teste_cadencia', sa.Boolean),
    sa.column('permite_auto_aprovacao', sa.Boolean),
    sa.column('permite_webhook_relatorio', sa.Boolean),
    sa.column('permite_api_parceiros', sa.Boolean),
    sa.column('permite_subtenants', sa.Boolean),
    sa.column('permite_registro_oportunidade', sa.Boolean),
    sa.column('retencao_dias_relatorio', sa.Integer),
    sa.column('retencao_dias_auditoria', sa.Integer),
    sa.column('modulos_contratados', sa.JSON),
    sa.column('categoria', sa.String),
)

_PLANOS_SUITE = ("POC", "Teste", "Starter", "Professional", "Enterprise")

# Cada tupla: (nome, preco_mensal, max_usuarios, modulo)
_PLANOS_AVULSOS = [
    ("MAP Starter", 149.50, 5, "map"),
    ("MAP Professional", 269.10, 10, "map"),
    ("MAP Enterprise", 478.40, 20, "map"),
    ("PREDATOR Starter", 475.50, 5, "predator"),
    ("PREDATOR Professional", 855.90, 10, "predator"),
    ("PREDATOR Enterprise", 1521.60, 20, "predator"),
    ("CRM Starter", 299.50, 5, "crm"),
    ("CRM Professional", 539.10, 10, "crm"),
    ("CRM Enterprise", 958.40, 20, "crm"),
]


def upgrade() -> None:
    op.add_column('plano', sa.Column('modulos_contratados', sa.JSON(), nullable=False, server_default='[]'))
    op.add_column('plano', sa.Column('categoria', sa.String(), nullable=False, server_default='suite'))

    conn = op.get_bind()
    for nome in _PLANOS_SUITE:
        conn.execute(
            plano.update().where(plano.c.nome == nome).values(
                modulos_contratados=["map", "predator", "crm"], categoria="suite",
            )
        )

    for nome, preco_mensal, max_usuarios, modulo in _PLANOS_AVULSOS:
        conn.execute(
            plano.insert().values(
                nome=nome,
                # Franquia/enriquecimento/cadência/campanha só fazem sentido
                # pra quem tem PREDATOR — nos planos MAP/CRM avulsos ficam
                # em 0 (irrelevante: a rota já está bloqueada pelo módulo).
                franquia_contas_mes=0,
                max_usuarios=max_usuarios,
                preco_mensal=preco_mensal,
                visivel_self_service=True,
                limite_enriquecimento_site_semanal=0,
                limite_enriquecimento_contatos_semanal=0,
                limite_cadencias_mes=0,
                limite_campanhas_mes=0,
                permite_ab_teste_cadencia=False,
                permite_auto_aprovacao=False,
                permite_webhook_relatorio=False,
                permite_api_parceiros=False,
                permite_subtenants=False,
                permite_registro_oportunidade=False,
                retencao_dias_relatorio=30,
                retencao_dias_auditoria=90,
                modulos_contratados=[modulo],
                categoria="modulo",
            )
        )


def downgrade() -> None:
    conn = op.get_bind()
    nomes_avulsos = [nome for nome, _, _, _ in _PLANOS_AVULSOS]
    conn.execute(plano.delete().where(plano.c.nome.in_(nomes_avulsos)))

    op.drop_column('plano', 'categoria')
    op.drop_column('plano', 'modulos_contratados')
