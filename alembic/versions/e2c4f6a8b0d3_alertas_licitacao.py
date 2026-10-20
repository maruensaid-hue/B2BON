"""Alertas de licitações por regra/ICP (V5.2.1, Fase 4): regras, alertas únicos por (tenant, edital) e cursor por tenant.

Downgrade: remove as três tabelas e, com elas, regras, alertas e cursores (as licitações e o corpus não são tocados).

Revision ID: e2c4f6a8b0d3
Revises: d1b3e5a7c9f1
Create Date: 2026-10-20
"""
import sqlalchemy as sa
from alembic import op

revision = "e2c4f6a8b0d3"
down_revision = "d1b3e5a7c9f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "regra_alerta_licitacao",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("nome", sa.String(), nullable=False),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("icp_id", sa.Integer(), sa.ForeignKey("icp.id"), nullable=True),
        sa.Column("palavras_chave", sa.JSON(), nullable=False),
        sa.Column("palavras_excluir", sa.JSON(), nullable=False),
        sa.Column("ufs", sa.JSON(), nullable=False),
        sa.Column("modalidades", sa.JSON(), nullable=False),
        sa.Column("valor_minimo", sa.Float(), nullable=True),
        sa.Column("valor_maximo", sa.Float(), nullable=True),
        sa.Column("dias_minimos_prazo", sa.Integer(), nullable=True),
        sa.Column("usar_portfolio", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("relevancia_minima", sa.Integer(), nullable=False, server_default="40"),
        sa.Column("frequencia", sa.String(), nullable=False, server_default="diaria"),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "nome", name="uq_regra_alerta_licitacao_tenant_nome"),
    )
    op.create_index("ix_regra_alerta_licitacao_tenant_id", "regra_alerta_licitacao", ["tenant_id"])
    op.create_index("ix_regra_alerta_licitacao_icp_id", "regra_alerta_licitacao", ["icp_id"])
    op.create_table(
        "alerta_licitacao",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("corpus_id", sa.Integer(), sa.ForeignKey("licitacao_publica.id"), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("fatores", sa.JSON(), nullable=False),
        sa.Column("regras", sa.JSON(), nullable=False),
        sa.Column("motivo", sa.String(), nullable=False, server_default="nova"),
        sa.Column("estado", sa.String(), nullable=False, server_default="novo"),
        sa.Column("versao_corpus", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("situacao_externa", sa.String(), nullable=True),
        sa.Column("atualizacao_nao_vista", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("entrega_estado", sa.String(), nullable=False, server_default="pendente"),
        sa.Column("entrega_tentativas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("entrega_ultimo_erro", sa.Text(), nullable=True),
        sa.Column("entregue_em", sa.DateTime(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("visto_em", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("tenant_id", "corpus_id", name="uq_alerta_licitacao_tenant_corpus"),
    )
    op.create_index("ix_alerta_licitacao_tenant_id", "alerta_licitacao", ["tenant_id"])
    op.create_index("ix_alerta_licitacao_corpus_id", "alerta_licitacao", ["corpus_id"])
    op.create_index("ix_alerta_licitacao_estado", "alerta_licitacao", ["estado"])
    op.create_table(
        "estado_alertas_licitacao",
        sa.Column("tenant_id", sa.String(), primary_key=True),
        sa.Column("ultimo_evento_id", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avaliado_em", sa.DateTime(), nullable=True),
        sa.Column("ultimo_resumo_em", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("estado_alertas_licitacao")
    op.drop_index("ix_alerta_licitacao_estado", table_name="alerta_licitacao")
    op.drop_index("ix_alerta_licitacao_corpus_id", table_name="alerta_licitacao")
    op.drop_index("ix_alerta_licitacao_tenant_id", table_name="alerta_licitacao")
    op.drop_table("alerta_licitacao")
    op.drop_index("ix_regra_alerta_licitacao_icp_id", table_name="regra_alerta_licitacao")
    op.drop_index("ix_regra_alerta_licitacao_tenant_id", table_name="regra_alerta_licitacao")
    op.drop_table("regra_alerta_licitacao")
