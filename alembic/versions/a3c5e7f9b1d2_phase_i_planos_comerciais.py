"""Phase I (OI-021, D-059): planos comerciais aprovados pelo PO.

- `plano.tipo_preco`: FIXED (checkout self-service) ou STARTING_AT ("a partir de",
  venda assistida; nunca vai para o checkout).
- Planos, só com os valores aprovados (D-059), criados se ainda não existirem:
  B2B ON Bid Intelligence R$ 1.490/mês; B2B ON Strategic Sourcing R$ 2.990/mês com 5
  usuários; B2B ON Strategic Sourcing Enterprise a partir de R$ 5.990/mês (sob consulta).
  AI Credits incluídos ficam em `finops/comercial.FRANQUIAS` (25K, 50K, 100K).
- Public Procurement continua sem plano (PENDING_DEFINITION): nenhum preço é criado.

Revision ID: a3c5e7f9b1d2
Revises: f2c4e6a8b0d1
Create Date: 2026-09-26
"""

import sqlalchemy as sa

from alembic import op

revision = "a3c5e7f9b1d2"
down_revision = "f2c4e6a8b0d1"
branch_labels = None
depends_on = None

# (nome, preço mensal, usuários incluídos — None = não definido pelo PO, módulos, self-service, tipo de preço)
PLANOS = (
    ("Bid Intelligence", 1490.0, None, ["bids"], True, "FIXED"),
    ("Strategic Sourcing", 2990.0, 5, ["sourcing"], True, "FIXED"),
    ("Strategic Sourcing Enterprise", 5990.0, None, ["sourcing", "sourcing_enterprise"], False, "STARTING_AT"),
)


def upgrade() -> None:
    op.add_column("plano", sa.Column("tipo_preco", sa.String(), nullable=False, server_default="FIXED"))
    conn = op.get_bind()
    plano = sa.table(
        "plano", sa.column("nome", sa.String), sa.column("franquia_contas_mes", sa.Integer), sa.column("max_usuarios", sa.Integer),
        sa.column("preco_mensal", sa.Float), sa.column("visivel_self_service", sa.Boolean), sa.column("modulos_contratados", sa.JSON),
        sa.column("categoria", sa.String), sa.column("tipo_preco", sa.String),
    )
    novos = [
        {"nome": nome, "franquia_contas_mes": 0, "max_usuarios": usuarios, "preco_mensal": preco, "visivel_self_service": self_service,
         "modulos_contratados": modulos, "categoria": "modulo", "tipo_preco": tipo}
        for nome, preco, usuarios, modulos, self_service, tipo in PLANOS
        if conn.execute(sa.text("SELECT 1 FROM plano WHERE nome = :nome"), {"nome": nome}).first() is None
    ]
    if novos:
        op.bulk_insert(plano, novos)


def downgrade() -> None:
    conn = op.get_bind()
    for nome, *_ in PLANOS:
        em_uso = conn.execute(sa.text("SELECT 1 FROM licenca l JOIN plano p ON p.id = l.plano_id WHERE p.nome = :nome"),
                              {"nome": nome}).first()
        if em_uso is None:
            conn.execute(sa.text("DELETE FROM plano WHERE nome = :nome"), {"nome": nome})
    op.drop_column("plano", "tipo_preco")
