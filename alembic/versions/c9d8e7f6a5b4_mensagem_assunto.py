"""Mensagem - adiciona assunto (so e-mail)

Raio-X 2026-09-24: a IA passa a gerar um assunto junto com o corpo da
mensagem quando o canal e email (visao rica de negocio/Aprovacoes).
Fica nulo pra whatsapp/linkedin e pra mensagens de email geradas antes
desta coluna existir - nunca inventamos um assunto pra dado antigo.

Revision ID: c9d8e7f6a5b4
Revises: b5a3d9c48786
Create Date: 2026-09-24

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9d8e7f6a5b4"
down_revision: Union[str, None] = "b5a3d9c48786"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("mensagem", sa.Column("assunto", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("mensagem", "assunto")
