"""Formulário público de pré-reserva de data: configuração por tenant e as pré-reservas (que nascem junto com conta, contato e negócio no CRM).

Duas tabelas novas e vazias; nenhum dado existente muda. As duas são de cada tenant e nascem com RLS (tenant direto + `rls_privilegiado`).

Revision ID: c7e9a1b3d5f7
Revises: b6d8f0a2c4e7
Create Date: 2026-11-11
"""
from alembic import op
import sqlalchemy as sa

from app.db import rls_sql

revision = "c7e9a1b3d5f7"
down_revision = "b6d8f0a2c4e7"
branch_labels = None
depends_on = None

_TABELAS = ("configuracao_pre_reserva", "pre_reserva")


def upgrade() -> None:
    op.create_table(
        "configuracao_pre_reserva",
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), primary_key=True),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("marca", sa.String(), nullable=False),
        sa.Column("titulo", sa.String(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("site", sa.String(), nullable=True),
        sa.Column("datas_disponiveis", sa.JSON(), nullable=False),
        sa.Column("antecedencia_minima_dias", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("horas_pre_reserva", sa.Integer(), nullable=False, server_default="48"),
        sa.Column("valor_presencial", sa.Float(), nullable=True),
        sa.Column("valor_online", sa.Float(), nullable=True),
        sa.Column("percentual_sinal", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("formas_pagamento", sa.JSON(), nullable=False),
        sa.Column("condicao_especial", sa.Text(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "pre_reserva",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("conta_id", sa.Integer(), sa.ForeignKey("conta.id"), nullable=False),
        sa.Column("decisor_id", sa.Integer(), sa.ForeignKey("decisor.id"), nullable=False),
        sa.Column("negocio_id", sa.Integer(), sa.ForeignKey("negocio.id"), nullable=False),
        sa.Column("data_evento", sa.Date(), nullable=False),
        sa.Column("formato", sa.String(), nullable=False),
        sa.Column("cidade", sa.String(), nullable=True),
        sa.Column("participantes", sa.Integer(), nullable=True),
        sa.Column("forma_pagamento", sa.String(), nullable=True),
        sa.Column("observacoes", sa.Text(), nullable=True),
        sa.Column("valor", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(), nullable=False, server_default="pre_reservada"),
        sa.Column("expira_em", sa.DateTime(), nullable=False),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pre_reserva_tenant_id", "pre_reserva", ["tenant_id"])
    op.create_index(
        "ix_pre_reserva_data_ativa_unica",
        "pre_reserva",
        ["tenant_id", "data_evento"],
        unique=True,
        postgresql_where=sa.text("status != 'cancelada'"),
        sqlite_where=sa.text("status != 'cancelada'"),
    )

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
    op.drop_index("ix_pre_reserva_data_ativa_unica", table_name="pre_reserva")
    op.drop_index("ix_pre_reserva_tenant_id", table_name="pre_reserva")
    op.drop_table("pre_reserva")
    op.drop_table("configuracao_pre_reserva")
