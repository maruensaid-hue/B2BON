"""D-087: escrita no CRM do cliente (PREDATOR/MAP → Salesforce, HubSpot, Pipedrive, RD Station).

- `conexao_integracao`: `escrita` (opt-in por capacidade), `webhook_token_hash`, `sync_solicitado_em`.
- `vinculo_externo`: id interno ↔ id no CRM (idempotência).
- `envio_crm`: fila de saída por conexão.
- `registro_crm_externo`: índice por hash (CNPJ/domínio/e-mail) para deduplicar a prospecção.
- `autorizacao_oauth_pendente`: tokens do callback OAuth aguardando o usuário que iniciou.

Revision ID: e3a5c7f9b1d4
Revises: d1f3b5c7e9a2
Create Date: 2026-10-04
"""

import sqlalchemy as sa

from alembic import op

revision = "e3a5c7f9b1d4"
down_revision = "d1f3b5c7e9a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("conexao_integracao") as tabela:
        tabela.add_column(sa.Column("escrita", sa.JSON(), nullable=True))
        tabela.add_column(sa.Column("webhook_token_hash", sa.String(), nullable=True))
        tabela.add_column(sa.Column("sync_solicitado_em", sa.DateTime(), nullable=True))
        tabela.create_index("ix_conexao_integracao_webhook_token_hash", ["webhook_token_hash"])

    op.create_table(
        "vinculo_externo",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("conexao_id", sa.Integer(), sa.ForeignKey("conexao_integracao.id"), nullable=False),
        sa.Column("entidade", sa.String(), nullable=False),
        sa.Column("id_interno", sa.String(), nullable=False),
        sa.Column("id_externo", sa.String(), nullable=False),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("conexao_id", "entidade", "id_interno", name="uq_vinculo_externo"),
    )
    op.create_index("ix_vinculo_externo_tenant_id", "vinculo_externo", ["tenant_id"])
    op.create_index("ix_vinculo_externo_conexao_id", "vinculo_externo", ["conexao_id"])

    op.create_table(
        "envio_crm",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("conexao_id", sa.Integer(), sa.ForeignKey("conexao_integracao.id"), nullable=False),
        sa.Column("operacao", sa.String(), nullable=False),
        sa.Column("id_interno", sa.String(), nullable=False),
        sa.Column("chave", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("tentativas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("proxima_tentativa_em", sa.DateTime(), nullable=True),
        sa.Column("ultimo_erro", sa.String(), nullable=True),
        sa.Column("resultado", sa.String(), nullable=True),
        sa.Column("ator_id", sa.String(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("enviado_em", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("conexao_id", "chave", name="uq_envio_crm_chave"),
    )
    op.create_index("ix_envio_crm_tenant_id", "envio_crm", ["tenant_id"])
    op.create_index("ix_envio_crm_conexao_id", "envio_crm", ["conexao_id"])
    op.create_index("ix_envio_crm_status", "envio_crm", ["status"])
    op.create_index("ix_envio_crm_proxima_tentativa_em", "envio_crm", ["proxima_tentativa_em"])

    op.create_table(
        "registro_crm_externo",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("conexao_id", sa.Integer(), sa.ForeignKey("conexao_integracao.id"), nullable=False),
        sa.Column("tipo_chave", sa.String(), nullable=False),
        sa.Column("chave_hash", sa.String(), nullable=False),
        sa.Column("cliente", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("negocio_aberto", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("optout", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("id_externo", sa.String(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("conexao_id", "tipo_chave", "chave_hash", name="uq_registro_crm_externo"),
    )
    op.create_index("ix_registro_crm_externo_tenant_id", "registro_crm_externo", ["tenant_id"])
    op.create_index("ix_registro_crm_externo_conexao_id", "registro_crm_externo", ["conexao_id"])
    op.create_index("ix_registro_crm_externo_chave_hash", "registro_crm_externo", ["chave_hash"])

    op.create_table(
        "autorizacao_oauth_pendente",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=False),
        sa.Column("sistema", sa.String(), nullable=False),
        sa.Column("nome", sa.String(), nullable=False),
        sa.Column("credenciais", sa.String(), nullable=False),
        sa.Column("expira_em", sa.DateTime(), nullable=False),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_autorizacao_oauth_pendente_tenant_id", "autorizacao_oauth_pendente", ["tenant_id"])
    op.create_index("ix_autorizacao_oauth_pendente_usuario_id", "autorizacao_oauth_pendente", ["usuario_id"])


def downgrade() -> None:
    op.drop_index("ix_autorizacao_oauth_pendente_usuario_id", table_name="autorizacao_oauth_pendente")
    op.drop_index("ix_autorizacao_oauth_pendente_tenant_id", table_name="autorizacao_oauth_pendente")
    op.drop_table("autorizacao_oauth_pendente")
    for indice in ("chave_hash", "conexao_id", "tenant_id"):
        op.drop_index(f"ix_registro_crm_externo_{indice}", table_name="registro_crm_externo")
    op.drop_table("registro_crm_externo")
    for indice in ("proxima_tentativa_em", "status", "conexao_id", "tenant_id"):
        op.drop_index(f"ix_envio_crm_{indice}", table_name="envio_crm")
    op.drop_table("envio_crm")
    for indice in ("conexao_id", "tenant_id"):
        op.drop_index(f"ix_vinculo_externo_{indice}", table_name="vinculo_externo")
    op.drop_table("vinculo_externo")
    with op.batch_alter_table("conexao_integracao") as tabela:
        tabela.drop_index("ix_conexao_integracao_webhook_token_hash")
        tabela.drop_column("sync_solicitado_em")
        tabela.drop_column("webhook_token_hash")
        tabela.drop_column("escrita")
