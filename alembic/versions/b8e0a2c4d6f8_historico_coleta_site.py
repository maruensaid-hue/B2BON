"""Histórico das coletas de site (verificação de domínio) e indicadores financeiros públicos com origem.

Revision ID: b8e0a2c4d6f8
Revises: a7d9f1b3c5e7
Create Date: 2026-10-20
"""
from alembic import op
import sqlalchemy as sa

revision = "b8e0a2c4d6f8"
down_revision = "a7d9f1b3c5e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "coleta_site_conta",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("conta_id", sa.Integer(), sa.ForeignKey("conta.id"), nullable=False),
        sa.Column("dominio", sa.String(), nullable=True),
        sa.Column("disparo", sa.String(), nullable=False),
        sa.Column("reprocesso_de_id", sa.Integer(), sa.ForeignKey("coleta_site_conta.id"), nullable=True),
        sa.Column("estado", sa.String(), nullable=False),
        sa.Column("iniciada_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("concluida_em", sa.DateTime(), nullable=True),
        sa.Column("paginas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fontes", sa.JSON(), nullable=False),
        sa.Column("resumo", sa.Text(), nullable=True),
        sa.Column("erro", sa.String(), nullable=True),
        sa.Column("avisos", sa.JSON(), nullable=False),
        sa.Column("dominio_origem", sa.String(), nullable=True),
        sa.Column("dominio_situacao", sa.String(), nullable=True),
        sa.Column("dominio_pontuacao", sa.Integer(), nullable=True),
        sa.Column("dominio_evidencias", sa.JSON(), nullable=False),
        sa.Column("dominio_limitacoes", sa.JSON(), nullable=False),
        sa.Column("dominio_validado_por", sa.String(), nullable=True),
        sa.Column("dominio_validado_em", sa.DateTime(), nullable=True),
        sa.Column("financeiro_estado", sa.String(), nullable=True),
    )
    op.create_index("ix_coleta_site_conta_tenant_id", "coleta_site_conta", ["tenant_id"])
    op.create_index("ix_coleta_site_conta_conta_id", "coleta_site_conta", ["conta_id"])
    op.create_index("ix_coleta_site_conta_reprocesso_de_id", "coleta_site_conta", ["reprocesso_de_id"])
    op.create_table(
        "indicador_financeiro_conta",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("conta_id", sa.Integer(), sa.ForeignKey("conta.id"), nullable=False),
        sa.Column("coleta_id", sa.Integer(), sa.ForeignKey("coleta_site_conta.id"), nullable=False),
        sa.Column("nome", sa.String(), nullable=False),
        sa.Column("tipo", sa.String(), nullable=False),
        sa.Column("valor", sa.Float(), nullable=False),
        sa.Column("moeda", sa.String(), nullable=False),
        sa.Column("escala", sa.String(), nullable=False),
        sa.Column("valor_original", sa.String(), nullable=False),
        sa.Column("periodo", sa.String(), nullable=True),
        sa.Column("url_fonte", sa.String(), nullable=False),
        sa.Column("trecho", sa.Text(), nullable=False),
        sa.Column("data_publicacao", sa.DateTime(), nullable=True),
        sa.Column("metodo_extracao", sa.String(), nullable=False),
        sa.Column("confianca", sa.String(), nullable=False),
        sa.Column("estado_validacao", sa.String(), nullable=False),
        sa.Column("formula", sa.String(), nullable=True),
        sa.Column("origens", sa.JSON(), nullable=False),
        sa.Column("coletado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_indicador_financeiro_conta_tenant_id", "indicador_financeiro_conta", ["tenant_id"])
    op.create_index("ix_indicador_financeiro_conta_conta_id", "indicador_financeiro_conta", ["conta_id"])
    op.create_index("ix_indicador_financeiro_conta_coleta_id", "indicador_financeiro_conta", ["coleta_id"])


def downgrade() -> None:
    op.drop_table("indicador_financeiro_conta")
    op.drop_table("coleta_site_conta")
