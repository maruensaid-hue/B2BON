"""Webmail: EmailDireto + configuracao pessoal do vendedor em Usuario

Raio-X 2026-09-24: agente de e-mail direto pra comunicacao com leads
do CRM ("like a Gmail") - compor/enviar/historico por conta, sem
passar pela fila de aprovacao de cadencia (o vendedor ja escreveu e
revisou sozinho). Configuravel por vendedor = nome de exibicao +
assinatura pessoal, mesmo molde de `Usuario.whatsapp_pessoal`.

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-09-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e3f4a5b6c7d8"
down_revision: Union[str, None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("usuario", sa.Column("email_nome_exibicao", sa.String(), nullable=True))
    op.add_column("usuario", sa.Column("email_assinatura", sa.String(), nullable=True))

    op.create_table(
        "email_direto",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("remetente_usuario_id", sa.Integer(), nullable=False),
        sa.Column("decisor_id", sa.Integer(), nullable=False),
        sa.Column("conta_id", sa.Integer(), nullable=False),
        sa.Column("assunto", sa.String(), nullable=False),
        sa.Column("corpo", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("motivo_falha", sa.String(), nullable=True),
        sa.Column("enviado_em", sa.DateTime(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(["remetente_usuario_id"], ["usuario.id"]),
        sa.ForeignKeyConstraint(["decisor_id"], ["decisor.id"]),
        sa.ForeignKeyConstraint(["conta_id"], ["conta.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_email_direto_tenant_id", "email_direto", ["tenant_id"])
    op.create_index("ix_email_direto_conta_id", "email_direto", ["conta_id"])


def downgrade() -> None:
    op.drop_index("ix_email_direto_conta_id", table_name="email_direto")
    op.drop_index("ix_email_direto_tenant_id", table_name="email_direto")
    op.drop_table("email_direto")
    op.drop_column("usuario", "email_assinatura")
    op.drop_column("usuario", "email_nome_exibicao")
