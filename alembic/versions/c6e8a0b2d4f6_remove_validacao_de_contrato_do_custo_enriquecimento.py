"""Enriquecimento: remove a etapa de "validação de contrato" do custo do provedor.

As decisões comerciais do provedor de contatos (custo, créditos, câmbio de planejamento, preços dos pacotes) já foram aprovadas pelo PO e não dependem de nova validação
contratual. A medição vem da resposta do provedor e a conciliação, do uso que ele informa. Remove as colunas criadas por `b5d7f9a1c3e5` para esse fim
(`contrato_validado_*`, `contrato_checklist`, `contrato_evidencia`, `saldo_transferivel`), todas nulas em qualquer ambiente que nunca usou a validação.

Downgrade: recria as colunas (nulas).

Revision ID: c6e8a0b2d4f6
Revises: b5d7f9a1c3e5
Create Date: 2026-10-21
"""
import sqlalchemy as sa
from alembic import op

revision = "c6e8a0b2d4f6"
down_revision = "b5d7f9a1c3e5"
branch_labels = None
depends_on = None

_COLUNAS = (
    ("contrato_validado_por", sa.String()),
    ("contrato_validado_em", sa.DateTime()),
    ("contrato_checklist", sa.JSON()),
    ("contrato_evidencia", sa.String()),
    ("saldo_transferivel", sa.Boolean()),
)


def upgrade() -> None:
    with op.batch_alter_table("enriquecimento_custo_provedor") as lote:
        for nome, _ in _COLUNAS:
            lote.drop_column(nome)


def downgrade() -> None:
    with op.batch_alter_table("enriquecimento_custo_provedor") as lote:
        for nome, tipo in _COLUNAS:
            lote.add_column(sa.Column(nome, tipo, nullable=True))
