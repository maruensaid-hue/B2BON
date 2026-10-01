"""D-074: comissão sobre a Margem Comissionável Líquida (correção definitiva do PO).

- Tax Profile (`perfil_tributario`) e Infrastructure Cost Model (`modelo_custo_infra`), com vigência; nenhum valor criado
  (o PO parametriza).
- `apuracao_comissao`: memória de cálculo por recebimento (receita bruta → impostos → infraestrutura → margem).
- `comissao_representante`: liga à apuração, ganha o ciclo de status (AWAITING_COST_PARAMETERS → CALCULATED → ACCRUED →
  PAYABLE → PAID) e perde as colunas da D-073 (substituída). Comissões ainda não pagas calculadas sobre o valor bruto
  voltam a AWAITING_COST_PARAMETERS, guardando o valor antigo em `valor_bruto_legado`; pagas ficam como estão.
- Política `BASE_LIQUIDA` (D-073) removida.

Revision ID: f4a6b8c0d2e3
Revises: e1f3a5b7c9d2
Create Date: 2026-10-01
"""

import sqlalchemy as sa

from alembic import op

revision = "f4a6b8c0d2e3"
down_revision = "e1f3a5b7c9d2"
branch_labels = None
depends_on = None

STATUS = {"paga": "PAID", "falhou": "FAILED", "estornada": "REVERSED", "a_compensar": "CLAWBACK_PENDING",
          "pendente_parametros": "AWAITING_COST_PARAMETERS"}
DINHEIRO = sa.Numeric(14, 2)


def upgrade() -> None:
    op.create_table(
        "perfil_tributario", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("regime", sa.String(), nullable=False),
        sa.Column("vigente_de", sa.Date(), nullable=False), sa.Column("vigente_ate", sa.Date(), nullable=True),
        sa.Column("tipo_receita", sa.String(), nullable=False), sa.Column("municipio", sa.String(), nullable=True),
        sa.Column("componentes", sa.JSON(), nullable=False), sa.Column("aliquota_efetiva", sa.Float(), nullable=False),
        sa.Column("metodo_calculo", sa.String(), nullable=False), sa.Column("fonte", sa.String(), nullable=True),
        sa.Column("observacoes", sa.String(), nullable=True), sa.Column("criado_por", sa.String(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "modelo_custo_infra", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("nome", sa.String(), nullable=False),
        sa.Column("vigente_de", sa.Date(), nullable=False), sa.Column("vigente_ate", sa.Date(), nullable=True),
        sa.Column("metodo", sa.String(), nullable=False), sa.Column("componentes", sa.JSON(), nullable=False),
        sa.Column("fonte", sa.String(), nullable=True), sa.Column("observacoes", sa.String(), nullable=True),
        sa.Column("criado_por", sa.String(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "apuracao_comissao", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False, index=True),
        sa.Column("origem", sa.String(), nullable=False),
        sa.Column("pagamento_licenca_id", sa.Integer(), sa.ForeignKey("pagamento_licenca.id"), nullable=True, unique=True),
        sa.Column("recebimento_governo_id", sa.Integer(), sa.ForeignKey("recebimento_governo.id"), nullable=True, unique=True),
        sa.Column("segmento", sa.String(), nullable=False), sa.Column("produto", sa.String(), nullable=False),
        sa.Column("tipo_receita", sa.String(), nullable=False), sa.Column("componente_tipo", sa.String(), nullable=True),
        sa.Column("recebido_em", sa.Date(), nullable=False), sa.Column("receita_bruta", DINHEIRO, nullable=False),
        sa.Column("perfil_tributario_id", sa.Integer(), sa.ForeignKey("perfil_tributario.id"), nullable=True, index=True),
        sa.Column("aliquota_tributaria", sa.Float(), nullable=True), sa.Column("impostos", DINHEIRO, nullable=True),
        sa.Column("modelo_custo_infra_id", sa.Integer(), sa.ForeignKey("modelo_custo_infra.id"), nullable=True, index=True),
        sa.Column("custo_infra", DINHEIRO, nullable=True), sa.Column("custo_ia", DINHEIRO, nullable=True),
        sa.Column("custo_ia_ate", sa.DateTime(), nullable=True), sa.Column("margem_comissionavel_liquida", DINHEIRO, nullable=True),
        sa.Column("status", sa.String(), nullable=False), sa.Column("parametros_faltantes", sa.JSON(), nullable=True),
        sa.Column("detalhe", sa.JSON(), nullable=True), sa.Column("calculado_em", sa.DateTime(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    with op.batch_alter_table("comissao_representante") as tabela:
        tabela.add_column(sa.Column("apuracao_id", sa.Integer(), nullable=True))
        for nome in ("calculado_em", "provisionado_em", "pagavel_em"):
            tabela.add_column(sa.Column(nome, sa.DateTime(), nullable=True))
        tabela.add_column(sa.Column("valor_bruto_legado", sa.Float(), nullable=True))
        tabela.create_foreign_key("fk_comissao_apuracao", "apuracao_comissao", ["apuracao_id"], ["id"])
        tabela.create_index("ix_comissao_representante_apuracao_id", ["apuracao_id"])
        tabela.drop_column("deducoes")
        tabela.drop_column("base_bruta")
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE comissao_representante SET valor_bruto_legado = valor_comissao, valor_comissao = 0, "
                         "status = 'AWAITING_COST_PARAMETERS' WHERE status = 'calculada'"))
    for antigo, novo in STATUS.items():
        conn.execute(sa.text("UPDATE comissao_representante SET status = :novo WHERE status = :antigo"), {"novo": novo, "antigo": antigo})
    conn.execute(sa.text("DELETE FROM politica_comissao WHERE codigo = 'BASE_LIQUIDA'"))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE comissao_representante SET valor_comissao = valor_bruto_legado, status = 'calculada' "
                         "WHERE valor_bruto_legado IS NOT NULL AND status = 'AWAITING_COST_PARAMETERS'"))
    for antigo, novo in STATUS.items():
        conn.execute(sa.text("UPDATE comissao_representante SET status = :antigo WHERE status = :novo"), {"novo": novo, "antigo": antigo})
    conn.execute(sa.text("UPDATE comissao_representante SET status = 'calculada' WHERE status IN ('CALCULATED', 'ACCRUED', 'PAYABLE')"))
    politica = sa.table("politica_comissao", sa.column("codigo", sa.String), sa.column("versao", sa.Integer),
                        sa.column("regras", sa.JSON), sa.column("ativa", sa.Boolean), sa.column("motivo", sa.String),
                        sa.column("criado_por", sa.String))
    op.bulk_insert(politica, [{"codigo": "BASE_LIQUIDA", "versao": 1, "regras": {"impostos": None, "infraestrutura": None},
                               "ativa": True, "motivo": "D-073", "criado_por": "migracao"}])
    with op.batch_alter_table("comissao_representante") as tabela:
        tabela.add_column(sa.Column("base_bruta", sa.Float(), nullable=True))
        tabela.add_column(sa.Column("deducoes", sa.JSON(), nullable=True))
        tabela.drop_index("ix_comissao_representante_apuracao_id")
        tabela.drop_constraint("fk_comissao_apuracao", type_="foreignkey")
        for nome in ("valor_bruto_legado", "pagavel_em", "provisionado_em", "calculado_em", "apuracao_id"):
            tabela.drop_column(nome)
    for tabela in ("apuracao_comissao", "modelo_custo_infra", "perfil_tributario"):
        op.drop_table(tabela)
