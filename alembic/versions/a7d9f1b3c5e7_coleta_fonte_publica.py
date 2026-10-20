"""Coleta agendada de fontes públicas (PNCP): configuração por tenant e histórico de execuções.

Revision ID: a7d9f1b3c5e7
Revises: f6c8e0a2b4d6
Create Date: 2026-10-20
"""
from alembic import op
import sqlalchemy as sa

revision = "a7d9f1b3c5e7"
down_revision = "f6c8e0a2b4d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "configuracao_coleta_fonte",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("fonte", sa.String(), nullable=False),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("modalidades", sa.JSON(), nullable=False),
        sa.Column("ufs", sa.JSON(), nullable=False),
        sa.Column("palavras_chave", sa.JSON(), nullable=False),
        sa.Column("janela_dias", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("max_novas_por_execucao", sa.Integer(), nullable=False, server_default="200"),
        sa.Column("atualizado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "fonte", name="uq_configuracao_coleta_fonte_tenant_fonte"),
    )
    op.create_index("ix_configuracao_coleta_fonte_tenant_id", "configuracao_coleta_fonte", ["tenant_id"])
    op.create_table(
        "execucao_coleta_fonte",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("fonte", sa.String(), nullable=False),
        sa.Column("disparo", sa.String(), nullable=False),
        sa.Column("estado", sa.String(), nullable=False),
        sa.Column("iniciada_em", sa.DateTime(), nullable=False),
        sa.Column("concluida_em", sa.DateTime(), nullable=True),
        sa.Column("duracao_ms", sa.Integer(), nullable=True),
        sa.Column("consultados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inseridos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("atualizados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ignorados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("paginas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tentativas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("erro", sa.String(), nullable=True),
        sa.Column("data_inicial", sa.String(), nullable=True),
        sa.Column("data_final", sa.String(), nullable=True),
        sa.Column("cursor_referencia", sa.String(), nullable=True),
    )
    op.create_index("ix_execucao_coleta_fonte_tenant_id", "execucao_coleta_fonte", ["tenant_id"])
    op.create_index(
        "ix_execucao_coleta_fonte_uma_em_andamento", "execucao_coleta_fonte", ["tenant_id", "fonte"], unique=True,
        postgresql_where=sa.text("estado = 'em_andamento'"), sqlite_where=sa.text("estado = 'em_andamento'"),
    )


def downgrade() -> None:
    op.drop_index("ix_execucao_coleta_fonte_uma_em_andamento", table_name="execucao_coleta_fonte")
    op.drop_index("ix_execucao_coleta_fonte_tenant_id", table_name="execucao_coleta_fonte")
    op.drop_table("execucao_coleta_fonte")
    op.drop_index("ix_configuracao_coleta_fonte_tenant_id", table_name="configuracao_coleta_fonte")
    op.drop_table("configuracao_coleta_fonte")
