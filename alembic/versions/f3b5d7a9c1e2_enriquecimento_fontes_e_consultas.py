"""Gerenciador de recursos de enriquecimento: registro de fontes (franquia técnica e disjuntor) e log de consultas por empresa.

Duas tabelas novas e vazias; nenhum dado existente muda. `enriquecimento_fonte` é configuração de plataforma (sem tenant, entra em GLOBAIS);
`enriquecimento_consulta` é de cada tenant e nasce com RLS (tenant direto + `rls_privilegiado`, como as tabelas da segunda etapa).

Revision ID: f3b5d7a9c1e2
Revises: e2a4c6f8b0d1
Create Date: 2026-11-09
"""
from alembic import op
import sqlalchemy as sa

from app.db import rls_sql

revision = "f3b5d7a9c1e2"
down_revision = "e2a4c6f8b0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "enriquecimento_fonte",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("codigo", sa.String(), nullable=False, unique=True),
        sa.Column("camada", sa.String(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("prioridade", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("limite_mensal", sa.Integer(), nullable=True),
        sa.Column("periodo", sa.String(), nullable=True),
        sa.Column("consumido_periodo", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("permite_uso_comercial", sa.Boolean(), nullable=True),
        sa.Column("politica_uso", sa.String(), nullable=True),
        sa.Column("falhas_seguidas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("suspensa_ate", sa.DateTime(), nullable=True),
        sa.Column("ultima_consulta_em", sa.DateTime(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "enriquecimento_consulta",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("conta_id", sa.Integer(), sa.ForeignKey("conta.id"), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=True),
        sa.Column("fonte", sa.String(), nullable=False),
        sa.Column("camada", sa.String(), nullable=False),
        sa.Column("estado", sa.String(), nullable=False),
        sa.Column("motivo", sa.String(), nullable=True),
        sa.Column("encontrados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("novos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("creditos_fonte", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duracao_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_enriquecimento_consulta_tenant_id", "enriquecimento_consulta", ["tenant_id"])
    op.create_index("ix_enriquecimento_consulta_conta_id", "enriquecimento_consulta", ["conta_id"])
    op.create_index("ix_enriquecimento_consulta_item_id", "enriquecimento_consulta", ["item_id"])
    op.create_index("ix_enriquecimento_consulta_fonte", "enriquecimento_consulta", ["fonte"])
    op.create_index("ix_enriquecimento_consulta_criado_em", "enriquecimento_consulta", ["criado_em"])
    op.create_index("ix_enriq_consulta_tenant_conta_fonte", "enriquecimento_consulta", ["tenant_id", "conta_id", "fonte", "criado_em"])

    if op.get_bind().dialect.name == "postgresql":
        for comando in (
            *rls_sql.sql_habilitar("enriquecimento_consulta"),
            *rls_sql.sql_tenant_direto("enriquecimento_consulta"),
            *rls_sql.sql_privilegiado("enriquecimento_consulta"),
        ):
            op.execute(comando)
        # GRANT ao papel de execução não é preciso: `rls_sql.sql_papel_aplicacao` deixou privilégios padrão para tabela nova no schema.


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for comando in rls_sql.sql_reverter("enriquecimento_consulta"):
            op.execute(comando)
    op.drop_index("ix_enriq_consulta_tenant_conta_fonte", table_name="enriquecimento_consulta")
    op.drop_index("ix_enriquecimento_consulta_criado_em", table_name="enriquecimento_consulta")
    op.drop_index("ix_enriquecimento_consulta_fonte", table_name="enriquecimento_consulta")
    op.drop_index("ix_enriquecimento_consulta_item_id", table_name="enriquecimento_consulta")
    op.drop_index("ix_enriquecimento_consulta_conta_id", table_name="enriquecimento_consulta")
    op.drop_index("ix_enriquecimento_consulta_tenant_id", table_name="enriquecimento_consulta")
    op.drop_table("enriquecimento_consulta")
    op.drop_table("enriquecimento_fonte")
