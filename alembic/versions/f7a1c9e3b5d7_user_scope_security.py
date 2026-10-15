"""Add token version and ownership fields for user-scoped CRM data."""
from alembic import op
import sqlalchemy as sa

revision = "f7a1c9e3b5d7"
down_revision = "e2a4c6e8f0b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("usuario", sa.Column("token_version", sa.Integer(), server_default="0", nullable=False))
    for table, column, constraint in (
        ("icp", "criador_usuario_id", "fk_icp_criador_usuario_id_usuario"),
        ("conta", "criado_por_usuario_id", "fk_conta_criado_por_usuario_id_usuario"),
        ("decisor", "criado_por_usuario_id", "fk_decisor_criado_por_usuario_id_usuario"),
    ):
        with op.batch_alter_table(table) as batch_op:
            batch_op.add_column(sa.Column(column, sa.Integer(), nullable=True))
            batch_op.create_foreign_key(constraint, "usuario", [column], ["id"])


def downgrade() -> None:
    for table, column, constraint in (
        ("decisor", "criado_por_usuario_id", "fk_decisor_criado_por_usuario_id_usuario"),
        ("conta", "criado_por_usuario_id", "fk_conta_criado_por_usuario_id_usuario"),
        ("icp", "criador_usuario_id", "fk_icp_criador_usuario_id_usuario"),
    ):
        with op.batch_alter_table(table) as batch_op:
            batch_op.drop_constraint(constraint, type_="foreignkey")
            batch_op.drop_column(column)
    op.drop_column("usuario", "token_version")
