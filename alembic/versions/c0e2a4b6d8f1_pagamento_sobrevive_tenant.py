"""Exclusão definitiva de tenant: o histórico de pagamento sobrevive ao tenant.

`pagamento_licenca` fica fora da varredura de `tenant_service.apagar_dados` (retenção fiscal/contábil), mas a FK
`pagamento_licenca.tenant_id → tenant.id` impedia apagar qualquer tenant que já tivesse pago. Remove só a FK: a coluna e
o índice continuam (o id do tenant apagado fica como referência histórica).

Revision ID: c0e2a4b6d8f1
Revises: b9d1f3a5c7e0
Create Date: 2026-10-01
"""

import sqlalchemy as sa

from alembic import op

revision = "c0e2a4b6d8f1"
down_revision = "b9d1f3a5c7e0"
branch_labels = None
depends_on = None

# A FK foi criada sem nome; no Postgres ela se chama assim, e a convenção dá o mesmo nome no SQLite (batch).
_FK = "pagamento_licenca_tenant_id_fkey"
_CONVENCAO = {"fk": "%(table_name)s_%(column_0_name)s_fkey"}


def upgrade() -> None:
    with op.batch_alter_table("pagamento_licenca", naming_convention=_CONVENCAO) as tabela:
        tabela.drop_constraint(_FK, type_="foreignkey")


def downgrade() -> None:
    # Pagamentos de tenants já apagados impediriam recriar a FK; eles não têm para onde voltar.
    op.execute(sa.text("DELETE FROM pagamento_licenca WHERE tenant_id NOT IN (SELECT id FROM tenant)"))
    with op.batch_alter_table("pagamento_licenca", naming_convention=_CONVENCAO) as tabela:
        tabela.create_foreign_key(_FK, "tenant", ["tenant_id"], ["id"])
