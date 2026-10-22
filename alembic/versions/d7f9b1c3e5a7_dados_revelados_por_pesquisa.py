"""Pesquisa de decisores: dados a revelar escolhidos pelo usuário em cada pesquisa.

Até aqui o e-mail era revelado por uma constante no código (e o telefone nunca). Agora cada pesquisa guarda o que o usuário marcou (e-mail por padrão,
telefone, ou os dois), e cada empresa guarda quantos decisores vieram com o link do perfil no LinkedIn. Pesquisas anteriores ficam como "só e-mail", que
é o que de fato foram.

Downgrade: remove as colunas.

Revision ID: d7f9b1c3e5a7
Revises: c6e8a0b2d4f6
Create Date: 2026-10-22
"""
import sqlalchemy as sa
from alembic import op

revision = "d7f9b1c3e5a7"
down_revision = "c6e8a0b2d4f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("pesquisa_decisores") as lote:
        lote.add_column(sa.Column("revelar_emails", sa.Boolean(), nullable=False, server_default=sa.true()))
        lote.add_column(sa.Column("revelar_telefones", sa.Boolean(), nullable=False, server_default=sa.false()))
    with op.batch_alter_table("pesquisa_decisores_empresa") as lote:
        lote.add_column(sa.Column("decisores_com_linkedin", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("pesquisa_decisores_empresa") as lote:
        lote.drop_column("decisores_com_linkedin")
    with op.batch_alter_table("pesquisa_decisores") as lote:
        lote.drop_column("revelar_telefones")
        lote.drop_column("revelar_emails")
