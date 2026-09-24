"""Webmail: caixa de entrada (EmailRecebido) + arquivamento de conversa

Raio-X 2026-09-24: extensao do Webmail com area de "Recebidos" (via
retransmissao automatica de resposta do cliente, reply-to trocado pra
um endereco nosso) e botao de "arquivar" o historico de mensagens.

Revision ID: f4a5b6c7d8e9
Revises: e3f4a5b6c7d8
Create Date: 2026-09-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4a5b6c7d8e9"
down_revision: Union[str, None] = "e3f4a5b6c7d8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("email_direto", sa.Column("arquivado_em", sa.DateTime(), nullable=True))

    op.create_table(
        "email_recebido",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("decisor_id", sa.Integer(), nullable=True),
        sa.Column("conta_id", sa.Integer(), nullable=True),
        sa.Column("remetente_email", sa.String(), nullable=False),
        sa.Column("assunto", sa.String(), nullable=False),
        sa.Column("corpo", sa.String(), nullable=False),
        sa.Column("arquivado_em", sa.DateTime(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(["decisor_id"], ["decisor.id"]),
        sa.ForeignKeyConstraint(["conta_id"], ["conta.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_email_recebido_tenant_id", "email_recebido", ["tenant_id"])
    op.create_index("ix_email_recebido_conta_id", "email_recebido", ["conta_id"])


def downgrade() -> None:
    op.drop_index("ix_email_recebido_conta_id", table_name="email_recebido")
    op.drop_index("ix_email_recebido_tenant_id", table_name="email_recebido")
    op.drop_table("email_recebido")
    op.drop_column("email_direto", "arquivado_em")
