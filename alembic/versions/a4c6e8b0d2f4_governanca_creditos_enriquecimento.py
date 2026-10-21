"""Governança de créditos de enriquecimento (pesquisa de decisores): configuração versionada, razão append-only, pesquisa e orçamento global.

Só cria tabelas novas e vazias: nenhuma linha existente é tocada e nenhum saldo é inventado. Sem configuração de plano/orçamento, a pesquisa de
decisores fica bloqueada (falha segura) — os valores comerciais entram depois, por configuração administrativa.

Downgrade: remove as sete tabelas e, com elas, configuração, razão e pesquisas de enriquecimento. Os decisores já gravados e os créditos/
lotes de IA não são tocados. O razão é histórico financeiro: faça cópia antes de reverter em ambiente com uso.

Revision ID: a4c6e8b0d2f4
Revises: f3d5a7c9e1b4
Create Date: 2026-10-20
"""
import sqlalchemy as sa
from alembic import op

revision = "a4c6e8b0d2f4"
down_revision = "f3d5a7c9e1b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "enriquecimento_carteira",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False, unique=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "enriquecimento_config_plano",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plano_id", sa.Integer(), sa.ForeignKey("plano.id"), nullable=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=True),
        sa.Column("versao", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("franquia_creditos", sa.Integer(), nullable=True),
        sa.Column("periodicidade", sa.String(), nullable=True),
        sa.Column("decisores_por_empresa_padrao", sa.Integer(), nullable=True),
        sa.Column("decisores_por_empresa_max", sa.Integer(), nullable=True),
        sa.Column("itens_por_lote_max", sa.Integer(), nullable=True),
        sa.Column("limite_periodo_creditos", sa.Integer(), nullable=True),
        sa.Column("motivo", sa.String(), nullable=True),
        sa.Column("criado_por", sa.String(), nullable=True),
        sa.Column("valido_de", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("valido_ate", sa.DateTime(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("plano_id", "versao", name="uq_enriq_config_plano_versao"),
        sa.UniqueConstraint("tenant_id", "versao", name="uq_enriq_config_tenant_versao"),
    )
    op.create_index("ix_enriquecimento_config_plano_plano_id", "enriquecimento_config_plano", ["plano_id"])
    op.create_index("ix_enriquecimento_config_plano_tenant_id", "enriquecimento_config_plano", ["tenant_id"])
    op.create_table(
        "enriquecimento_orcamento_global",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provedor", sa.String(), nullable=False),
        sa.Column("versao", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("limite_creditos", sa.Integer(), nullable=True),
        sa.Column("alerta_percentual", sa.Integer(), nullable=False, server_default="80"),
        sa.Column("motivo", sa.String(), nullable=True),
        sa.Column("criado_por", sa.String(), nullable=True),
        sa.Column("valido_de", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("valido_ate", sa.DateTime(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("provedor", "versao", name="uq_enriq_orcamento_provedor_versao"),
    )
    op.create_index("ix_enriquecimento_orcamento_global_provedor", "enriquecimento_orcamento_global", ["provedor"])
    op.create_table(
        "pesquisa_decisores",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("provedor", sa.String(), nullable=False),
        sa.Column("estado", sa.String(), nullable=False),
        sa.Column("decisores_por_empresa", sa.Integer(), nullable=False),
        sa.Column("origem_decisores", sa.String(), nullable=False),
        sa.Column("config_origem", sa.String(), nullable=False),
        sa.Column("config_id", sa.Integer(), nullable=False),
        sa.Column("config_versao", sa.Integer(), nullable=False),
        sa.Column("total_empresas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_maximo", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimativa", sa.JSON(), nullable=False),
        sa.Column("selecao_hash", sa.String(), nullable=False),
        sa.Column("previa_expira_em", sa.DateTime(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("confirmada_por", sa.Integer(), nullable=True),
        sa.Column("confirmada_em", sa.DateTime(), nullable=True),
        sa.Column("creditos_reservados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("creditos_consumidos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("requer_reconciliacao", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("motivo", sa.String(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_pesquisa_decisores_idempotencia"),
    )
    op.create_index("ix_pesquisa_decisores_tenant_id", "pesquisa_decisores", ["tenant_id"])
    op.create_index("ix_pesquisa_decisores_estado", "pesquisa_decisores", ["estado"])
    op.create_index("ix_pesquisa_decisores_criado_em", "pesquisa_decisores", ["criado_em"])
    op.create_table(
        "pesquisa_decisores_empresa",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pesquisa_id", sa.String(), sa.ForeignKey("pesquisa_decisores.id"), nullable=False),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("conta_id", sa.Integer(), sa.ForeignKey("conta.id"), nullable=False),
        sa.Column("estado", sa.String(), nullable=False, server_default="pendente"),
        sa.Column("decisores_existentes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("decisores_solicitados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("decisores_retornados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("creditos_reservados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("creditos_consumidos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tentativas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ids_provedor", sa.JSON(), nullable=True),
        sa.Column("motivo", sa.String(), nullable=True),
        sa.Column("enviado_em", sa.DateTime(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("pesquisa_id", "conta_id", name="uq_pesquisa_decisores_empresa_conta"),
    )
    op.create_index("ix_pesquisa_decisores_empresa_pesquisa_id", "pesquisa_decisores_empresa", ["pesquisa_id"])
    op.create_index("ix_pesquisa_decisores_empresa_tenant_id", "pesquisa_decisores_empresa", ["tenant_id"])
    op.create_index("ix_pesquisa_decisores_empresa_conta_id", "pesquisa_decisores_empresa", ["conta_id"])
    op.create_table(
        "pesquisa_decisores_transicao",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pesquisa_id", sa.String(), sa.ForeignKey("pesquisa_decisores.id"), nullable=False),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=True),
        sa.Column("estado_anterior", sa.String(), nullable=True),
        sa.Column("estado_novo", sa.String(), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("ator_id", sa.String(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pesquisa_decisores_transicao_pesquisa_id", "pesquisa_decisores_transicao", ["pesquisa_id"])
    op.create_index("ix_pesquisa_decisores_transicao_tenant_id", "pesquisa_decisores_transicao", ["tenant_id"])
    op.create_table(
        "enriquecimento_movimento",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("tipo", sa.String(), nullable=False),
        sa.Column("delta_saldo", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("delta_reservado", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("disponivel_apos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provedor", sa.String(), nullable=True),
        sa.Column("periodo", sa.String(), nullable=True),
        sa.Column("pesquisa_id", sa.String(), sa.ForeignKey("pesquisa_decisores.id"), nullable=True),
        sa.Column("item_id", sa.Integer(), nullable=True),
        sa.Column("origem", sa.String(), nullable=True),
        sa.Column("motivo", sa.String(), nullable=True),
        sa.Column("ator_id", sa.String(), nullable=True),
        sa.Column("expira_em", sa.DateTime(), nullable=True),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_enriq_movimento_idempotencia"),
    )
    op.create_index("ix_enriquecimento_movimento_tenant_id", "enriquecimento_movimento", ["tenant_id"])
    op.create_index("ix_enriquecimento_movimento_tipo", "enriquecimento_movimento", ["tipo"])
    op.create_index("ix_enriquecimento_movimento_provedor", "enriquecimento_movimento", ["provedor"])
    op.create_index("ix_enriquecimento_movimento_pesquisa_id", "enriquecimento_movimento", ["pesquisa_id"])
    op.create_index("ix_enriquecimento_movimento_criado_em", "enriquecimento_movimento", ["criado_em"])


def downgrade() -> None:
    for tabela in ("enriquecimento_movimento", "pesquisa_decisores_transicao", "pesquisa_decisores_empresa", "pesquisa_decisores",
                   "enriquecimento_orcamento_global", "enriquecimento_config_plano", "enriquecimento_carteira"):
        op.drop_table(tabela)
