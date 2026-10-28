"""Envio por API do próprio cliente e rastreio de abertura/entrega nas campanhas.

- `configuracao_email_api`: chave de API, remetente e chave de verificação do webhook do serviço de envio de cada cliente (a chave fica cifrada).
- `campanha_destinatario.aberto_em` / `entregue_em` / `pixel_incluido`: abertura (pixel), entrega confirmada pelo serviço de envio e se o e-mail saiu com pixel
  (sem isso os envios antigos, que não tinham pixel, derrubariam a taxa de abertura).
- `mensagem.entregue_em`: entrega confirmada pelo serviço de envio, para os e-mails de cadência.

Tudo nullable ou com padrão: os registros existentes continuam como estavam.

Downgrade: remove as colunas e a tabela.

Revision ID: c1e3a5b7d9f4
Revises: f6b8d0e2a4c7
Create Date: 2026-10-27
"""
import sqlalchemy as sa
from alembic import op

revision = "c1e3a5b7d9f4"
down_revision = "f6b8d0e2a4c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Cria `configuracao_email_api` e as colunas de abertura/entrega (ver o resumo no topo do arquivo)."""
    op.create_table(
        "configuracao_email_api",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("chave_api", sa.String(), nullable=False),
        sa.Column("remetente_email", sa.String(), nullable=False),
        sa.Column("remetente_nome", sa.String(), nullable=True),
        sa.Column("chave_webhook", sa.String(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id"),
    )
    op.create_index("ix_configuracao_email_api_tenant_id", "configuracao_email_api", ["tenant_id"])

    with op.batch_alter_table("campanha_destinatario") as lote:
        lote.add_column(sa.Column("aberto_em", sa.DateTime(), nullable=True))
        lote.add_column(sa.Column("entregue_em", sa.DateTime(), nullable=True))
        lote.add_column(sa.Column("pixel_incluido", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("mensagem") as lote:
        lote.add_column(sa.Column("entregue_em", sa.DateTime(), nullable=True))


def downgrade() -> None:
    """Remove as colunas e a tabela (a configuração do envio por API e os registros de abertura/entrega são perdidos)."""
    with op.batch_alter_table("mensagem") as lote:
        lote.drop_column("entregue_em")
    with op.batch_alter_table("campanha_destinatario") as lote:
        lote.drop_column("pixel_incluido")
        lote.drop_column("entregue_em")
        lote.drop_column("aberto_em")
    op.drop_index("ix_configuracao_email_api_tenant_id", table_name="configuracao_email_api")
    op.drop_table("configuracao_email_api")
