"""Add token version and ownership fields for user-scoped CRM data."""
from alembic import op
import sqlalchemy as sa

revision = "f7a1c9e3b5d7"
down_revision = "e2a4c6e8f0b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("usuario", sa.Column("token_version", sa.Integer(), server_default="0", nullable=False))
    op.add_column("icp", sa.Column("criador_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True))
    op.add_column("conta", sa.Column("criado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True))
    op.add_column("decisor", sa.Column("criado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True))


def downgrade() -> None:
    op.drop_column("decisor", "criado_por_usuario_id")
    op.drop_column("conta", "criado_por_usuario_id")
    op.drop_column("icp", "criador_usuario_id")
    op.drop_column("usuario", "token_version")
