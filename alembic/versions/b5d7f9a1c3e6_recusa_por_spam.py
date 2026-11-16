"""Recusa por spam/bloqueio de reputacao: contador proprio e isencao por tenant.

`registro_reputacao_canal.recusas_spam` conta as recusas do servidor do destinatario por spam ou reputacao (separadas do e-mail inexistente).
`tenant.isento_pausa_spam` deixa o tenant fora da pausa automatica por essas recusas (os numeros continuam aparecendo no relatorio); so o super admin
liga. A CyberFort ja nasce isenta, por decisao do PO em 16/11/2026.

Revision ID: b5d7f9a1c3e6
Revises: a3c5e7f9b1d4
Create Date: 2026-11-16
"""
import sqlalchemy as sa

from alembic import op

revision = "b5d7f9a1c3e6"
down_revision = "a3c5e7f9b1d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("registro_reputacao_canal", sa.Column("recusas_spam", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("tenant", sa.Column("isento_pausa_spam", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute(sa.text("UPDATE tenant SET isento_pausa_spam = :sim WHERE id = 'cyberfort'").bindparams(sim=True))


def downgrade() -> None:
    op.drop_column("tenant", "isento_pausa_spam")
    op.drop_column("registro_reputacao_canal", "recusas_spam")
