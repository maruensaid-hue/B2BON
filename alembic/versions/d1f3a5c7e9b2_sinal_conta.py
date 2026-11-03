"""Sinais de conta (um fato por linha, com evidência), critérios de sinais no ICP, procedência do e-mail do decisor e
pausa da empresa inteira ao responder e prospecção automática (cadência), rascunho de resposta e link de agenda (comunicação),
WhatsApp sem template (Direct Send) e conexão do número pela Meta.

Cria `sinal_conta` já com RLS (tenant direto + `rls_privilegiado`, como as tabelas da segunda etapa) e a coluna `icp.criterios_sinais`.
Nenhum dado existente muda: a tabela começa vazia e se preenche no próximo enriquecimento de cada conta; ICP sem critério segue igual.

Revision ID: d1f3a5c7e9b2
Revises: a3c5e7b9d1f2
Create Date: 2026-11-03
"""
from alembic import op
import sqlalchemy as sa

from app.db import rls_sql

revision = "d1f3a5c7e9b2"
down_revision = "a3c5e7b9d1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sinal_conta",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("conta_id", sa.Integer(), sa.ForeignKey("conta.id"), nullable=False),
        sa.Column("codigo", sa.String(), nullable=False),
        sa.Column("valor_num", sa.Float(), nullable=True),
        sa.Column("valor_texto", sa.String(), nullable=True),
        sa.Column("confianca", sa.Float(), nullable=False),
        sa.Column("fonte", sa.String(), nullable=False),
        sa.Column("url_evidencia", sa.String(), nullable=True),
        sa.Column("trecho", sa.Text(), nullable=True),
        sa.Column("coleta_id", sa.Integer(), sa.ForeignKey("coleta_site_conta.id"), nullable=True),
        sa.Column("vigente", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("observado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_sinal_conta_tenant_id", "sinal_conta", ["tenant_id"])
    op.create_index("ix_sinal_conta_conta_id", "sinal_conta", ["conta_id"])
    op.create_index("ix_sinal_conta_codigo", "sinal_conta", ["codigo"])
    op.create_index("ix_sinal_conta_coleta_id", "sinal_conta", ["coleta_id"])
    op.create_index("ix_sinal_conta_conta_codigo_vigente", "sinal_conta", ["conta_id", "codigo", "vigente"])

    with op.batch_alter_table("icp") as batch:
        batch.add_column(sa.Column("criterios_sinais", sa.JSON(), nullable=True))
    with op.batch_alter_table("decisor") as batch:
        batch.add_column(sa.Column("email_status", sa.String(), nullable=True))
    with op.batch_alter_table("cadencia") as batch:
        batch.add_column(sa.Column("pausar_empresa_ao_responder", sa.Boolean(), nullable=False, server_default=sa.false()))
        batch.add_column(sa.Column("prospeccao_automatica", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("configuracao_comunicacao") as batch:
        batch.add_column(sa.Column("rascunho_resposta", sa.Boolean(), nullable=False, server_default=sa.true()))
        batch.add_column(sa.Column("link_agendamento", sa.String(), nullable=True))
    with op.batch_alter_table("configuracao_whatsapp") as batch:
        for coluna in ("origem_conexao", "pin_registro", "numero_exibicao", "nome_verificado", "qualidade", "direct_send_motivo_desligado"):
            batch.add_column(sa.Column(coluna, sa.String(), nullable=True))
        batch.add_column(sa.Column("direct_send_habilitado", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("toque_cadencia") as batch:
        batch.add_column(sa.Column("whatsapp_sem_template", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("cadencia") as batch:
        batch.add_column(sa.Column("direct_send_aceito_por", sa.String(), nullable=True))
        batch.add_column(sa.Column("direct_send_aceito_em", sa.DateTime(), nullable=True))
    with op.batch_alter_table("mensagem") as batch:
        batch.add_column(sa.Column("whatsapp_modo", sa.String(), nullable=True))
    op.execute("UPDATE icp SET criterios_sinais = '[]' WHERE criterios_sinais IS NULL")

    if op.get_bind().dialect.name == "postgresql":
        for comando in (*rls_sql.sql_habilitar("sinal_conta"), *rls_sql.sql_tenant_direto("sinal_conta"), *rls_sql.sql_privilegiado("sinal_conta")):
            op.execute(comando)
        # GRANT ao papel de execução não é preciso: `rls_sql.sql_papel_aplicacao` deixou privilégios padrão para tabela nova no schema.


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for comando in rls_sql.sql_reverter("sinal_conta"):
            op.execute(comando)
    with op.batch_alter_table("mensagem") as batch:
        batch.drop_column("whatsapp_modo")
    with op.batch_alter_table("cadencia") as batch:
        batch.drop_column("direct_send_aceito_em")
        batch.drop_column("direct_send_aceito_por")
    with op.batch_alter_table("toque_cadencia") as batch:
        batch.drop_column("whatsapp_sem_template")
    with op.batch_alter_table("configuracao_whatsapp") as batch:
        for coluna in ("direct_send_habilitado", "direct_send_motivo_desligado", "qualidade", "nome_verificado", "numero_exibicao", "pin_registro", "origem_conexao"):
            batch.drop_column(coluna)
    with op.batch_alter_table("configuracao_comunicacao") as batch:
        batch.drop_column("link_agendamento")
        batch.drop_column("rascunho_resposta")
    with op.batch_alter_table("cadencia") as batch:
        batch.drop_column("prospeccao_automatica")
        batch.drop_column("pausar_empresa_ao_responder")
    with op.batch_alter_table("decisor") as batch:
        batch.drop_column("email_status")
    with op.batch_alter_table("icp") as batch:
        batch.drop_column("criterios_sinais")
    op.drop_index("ix_sinal_conta_conta_codigo_vigente", table_name="sinal_conta")
    op.drop_index("ix_sinal_conta_coleta_id", table_name="sinal_conta")
    op.drop_index("ix_sinal_conta_codigo", table_name="sinal_conta")
    op.drop_index("ix_sinal_conta_conta_id", table_name="sinal_conta")
    op.drop_index("ix_sinal_conta_tenant_id", table_name="sinal_conta")
    op.drop_table("sinal_conta")
