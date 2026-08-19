"""Hierarquia de tenants (Distribuidor -> Revendedor -> Cliente)

Revision ID: d29ee2efce52
Revises: 13bae6ae1404
Create Date: 2026-08-19 17:38:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd29ee2efce52'
down_revision: Union[str, Sequence[str], None] = '13bae6ae1404'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('tenant', sa.Column('tipo', sa.String(), nullable=False, server_default='cliente'))
    op.add_column('tenant', sa.Column('tenant_pai_id', sa.String(), nullable=True))
    op.add_column('tenant', sa.Column('modo_cobranca', sa.String(), nullable=False, server_default='direta'))
    op.create_foreign_key(
        'fk_tenant_tenant_pai_id_tenant', 'tenant', 'tenant', ['tenant_pai_id'], ['id']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_tenant_tenant_pai_id_tenant', 'tenant', type_='foreignkey')
    op.drop_column('tenant', 'modo_cobranca')
    op.drop_column('tenant', 'tenant_pai_id')
    op.drop_column('tenant', 'tipo')
