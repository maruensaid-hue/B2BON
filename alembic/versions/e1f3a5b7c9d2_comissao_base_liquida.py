"""D-073: comissão sobre o lucro líquido (todas as vendas) e adicionais Government a 10%.

- `comissao_representante` guarda a base bruta (valor recebido) e as deduções aplicadas; `base_calculo` passa a ser a
  base líquida (bruto − impostos − infraestrutura). Sem as alíquotas definidas, a comissão fica "pendente_parametros"
  (valor 0, nunca repassada) até o PO informar e a plataforma recalcular.
- Política de deduções `BASE_LIQUIDA` versão 1 com impostos e infraestrutura **vazios** (o PO não informou os valores).
- Política Government versão 2: serviços adicionais e AI Credits adicionais comissionáveis a 10% (decisão do PO).

Revision ID: e1f3a5b7c9d2
Revises: d9e1f3a5b7c9
Create Date: 2026-10-01
"""

import sqlalchemy as sa

from alembic import op

revision = "e1f3a5b7c9d2"
down_revision = "d9e1f3a5b7c9"
branch_labels = None
depends_on = None

DEDUCOES_V1 = {"impostos": None, "infraestrutura": None}
POLITICA_V2 = {
    "gatilho": "PAYMENT_RECEIVED",
    "componentes": {
        "LICENSE": {"comissionavel": True, "taxa": 0.20},
        "INITIAL_ANNUAL_SUBSCRIPTION": {"comissionavel": True, "taxa": 0.20},
        "RENEWAL_ANNUAL_SUBSCRIPTION": {"comissionavel": True, "taxa": 0.10},
        "IMPLEMENTATION": {"comissionavel": False, "taxa": 0.20},
        "ADDITIONAL_SERVICES": {"comissionavel": True, "taxa": 0.10},
        "ADDITIONAL_AI_CREDITS": {"comissionavel": True, "taxa": 0.10},
    },
}


def upgrade() -> None:
    with op.batch_alter_table("comissao_representante") as tabela:
        tabela.add_column(sa.Column("base_bruta", sa.Float(), nullable=True))
        tabela.add_column(sa.Column("deducoes", sa.JSON(), nullable=True))
    politica = sa.table("politica_comissao", sa.column("codigo", sa.String), sa.column("versao", sa.Integer),
                        sa.column("regras", sa.JSON), sa.column("ativa", sa.Boolean), sa.column("motivo", sa.String),
                        sa.column("criado_por", sa.String))
    conn = op.get_bind()
    versao = conn.execute(sa.text("SELECT max(versao) FROM politica_comissao WHERE codigo = 'GOVERNMENT'")).scalar() or 0
    conn.execute(sa.text("UPDATE politica_comissao SET ativa = :falso WHERE codigo = 'GOVERNMENT'"), {"falso": False})
    op.bulk_insert(politica, [
        {"codigo": "GOVERNMENT", "versao": versao + 1, "regras": POLITICA_V2, "ativa": True,
         "motivo": "Serviços e AI Credits adicionais comissionáveis a 10% (D-073)", "criado_por": "migracao"},
        {"codigo": "BASE_LIQUIDA", "versao": 1, "regras": DEDUCOES_V1, "ativa": True,
         "motivo": "Comissão sobre o lucro líquido; alíquotas a informar pelo PO (D-073)", "criado_por": "migracao"},
    ])


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM politica_comissao WHERE codigo = 'BASE_LIQUIDA'"))
    conn.execute(sa.text("DELETE FROM politica_comissao WHERE codigo = 'GOVERNMENT' AND criado_por = 'migracao' AND versao > 1"))
    conn.execute(sa.text("UPDATE politica_comissao SET ativa = :verdade WHERE codigo = 'GOVERNMENT' AND versao = "
                         "(SELECT max(versao) FROM politica_comissao WHERE codigo = 'GOVERNMENT')"), {"verdade": True})
    with op.batch_alter_table("comissao_representante") as tabela:
        tabela.drop_column("deducoes")
        tabela.drop_column("base_bruta")
