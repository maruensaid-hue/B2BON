"""Phase J3 (OI-023, D-071): usuários do B2B ON Bid Intelligence.

- Plano "Bid Intelligence": 10 usuários incluídos por tenant (`max_usuarios`), decisão do PO. Só preenche se ainda
  estiver indefinido (NULL), para não sobrescrever edição feita no Admin.
- `licenca.usuarios_adicionais` (additional_user_quantity): usuários além dos incluídos. O limite de assentos é
  incluídos + adicionais, lido pelo entitlement. Preço por usuário adicional: PENDING_DEFINITION (nenhum valor).

Revision ID: c5e7a9b1d3f4
Revises: a3c5e7f9b1d2
Create Date: 2026-09-26
"""

import sqlalchemy as sa

from alembic import op

revision = "c5e7a9b1d3f4"
down_revision = "a3c5e7f9b1d2"
branch_labels = None
depends_on = None

PLANO = "Bid Intelligence"
USUARIOS_INCLUIDOS = 10


def upgrade() -> None:
    op.add_column("licenca", sa.Column("usuarios_adicionais", sa.Integer(), nullable=False, server_default="0"))
    op.get_bind().execute(sa.text("UPDATE plano SET max_usuarios = :usuarios WHERE nome = :nome AND max_usuarios IS NULL"),
                          {"usuarios": USUARIOS_INCLUIDOS, "nome": PLANO})


def downgrade() -> None:
    op.get_bind().execute(sa.text("UPDATE plano SET max_usuarios = NULL WHERE nome = :nome AND max_usuarios = :usuarios"),
                          {"usuarios": USUARIOS_INCLUIDOS, "nome": PLANO})
    op.drop_column("licenca", "usuarios_adicionais")
