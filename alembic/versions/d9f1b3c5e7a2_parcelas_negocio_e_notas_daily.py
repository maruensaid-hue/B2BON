"""Parcelas a receber dos negócios ganhos (quadro de inadimplentes do MAP) e anotações da daily do gestor.

Duas tabelas novas e vazias; nenhum dado existente muda. As duas são de cada tenant e nascem com RLS (tenant direto + `rls_privilegiado`).

Revision ID: d9f1b3c5e7a2
Revises: b5d7f9a1c3e6
Create Date: 2026-11-18
"""
import sqlalchemy as sa

from alembic import op
from app.db import rls_sql

revision = "d9f1b3c5e7a2"
down_revision = "b5d7f9a1c3e6"
branch_labels = None
depends_on = None

_TABELAS = ("parcela_negocio", "nota_daily")


def upgrade() -> None:
    op.create_table(
        "parcela_negocio",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocio.id"), nullable=False),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("valor", sa.Float(), nullable=False),
        sa.Column("vencimento", sa.Date(), nullable=False),
        sa.Column("pago_em", sa.Date(), nullable=True),
        sa.Column("observacao", sa.String(), nullable=True),
        sa.Column("criado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_parcela_negocio_tenant_id", "parcela_negocio", ["tenant_id"])
    op.create_index("ix_parcela_negocio_negocio_id", "parcela_negocio", ["negocio_id"])
    op.create_index("ix_parcela_negocio_vencimento", "parcela_negocio", ["vencimento"])

    op.create_table(
        "nota_daily",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("autor_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("exibir_em", sa.Date(), nullable=False),
        sa.Column("concluida_em", sa.DateTime(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_nota_daily_tenant_id", "nota_daily", ["tenant_id"])
    op.create_index("ix_nota_daily_autor_usuario_id", "nota_daily", ["autor_usuario_id"])
    op.create_index("ix_nota_daily_exibir_em", "nota_daily", ["exibir_em"])

    if op.get_bind().dialect.name == "postgresql":
        for tabela in _TABELAS:
            for comando in (*rls_sql.sql_habilitar(tabela), *rls_sql.sql_tenant_direto(tabela), *rls_sql.sql_privilegiado(tabela)):
                op.execute(comando)
        # GRANT ao papel de execução não é preciso: `rls_sql.sql_papel_aplicacao` deixou privilégios padrão para tabela nova no schema.


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for tabela in _TABELAS:
            for comando in rls_sql.sql_reverter(tabela):
                op.execute(comando)
    op.drop_index("ix_nota_daily_exibir_em", table_name="nota_daily")
    op.drop_index("ix_nota_daily_autor_usuario_id", table_name="nota_daily")
    op.drop_index("ix_nota_daily_tenant_id", table_name="nota_daily")
    op.drop_table("nota_daily")
    op.drop_index("ix_parcela_negocio_vencimento", table_name="parcela_negocio")
    op.drop_index("ix_parcela_negocio_negocio_id", table_name="parcela_negocio")
    op.drop_index("ix_parcela_negocio_tenant_id", table_name="parcela_negocio")
    op.drop_table("parcela_negocio")
