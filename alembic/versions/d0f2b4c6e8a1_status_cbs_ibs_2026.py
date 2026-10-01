"""D-078: situação de CBS/IBS em 2026 por vigência (TaxStatusPeriod) — WAIVED_BY_COMPLIANCE.

- `periodo_status_tributario`: grupo, situação, vigência (fim inclusivo), motivo, aprovador, evidência, referência legal.
- 2026 (01/01 a 31/12): WAIVED_BY_COMPLIANCE — CyberFort cumprindo as obrigações acessórias de 2026. Alíquotas-teste
  preservadas nos Tax Profiles (CBS 0,90%, IBS 0,10%); imposto de caixa zero enquanto valer a dispensa.

Revision ID: d0f2b4c6e8a1
Revises: c8e0a2b4d6f9
Create Date: 2026-10-01
"""

from datetime import date

import sqlalchemy as sa

from alembic import op

revision = "d0f2b4c6e8a1"
down_revision = "c8e0a2b4d6f9"
branch_labels = None
depends_on = None

REFERENCIA_LEGAL = ("EC 132/2023 (ADCT, art. 125: em 2026 CBS 0,9% e IBS 0,1%, compensáveis com PIS/COFINS) e LC 214/2025 "
                    "(transição de 2026: dispensa do recolhimento da CBS/IBS para quem cumpre as obrigações acessórias)")
PERIODO_2026 = {"grupo": "CBS_IBS", "status": "WAIVED_BY_COMPLIANCE", "vigente_de": date(2026, 1, 1), "vigente_ate": date(2026, 12, 31),
                "motivo": "Configuração aprovada pelo PO para 2026: CyberFort cumprindo as obrigações acessórias aplicáveis",
                "aprovado_por": "Product Owner (2026-10-01)", "referencia_evidencia": "Resolução definitiva CBS/IBS 2026 (PO, 2026-10-01)",
                "referencia_legal": REFERENCIA_LEGAL, "criado_por": "migracao"}


def upgrade() -> None:
    op.create_table(
        "periodo_status_tributario", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("grupo", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False), sa.Column("vigente_de", sa.Date(), nullable=False),
        sa.Column("vigente_ate", sa.Date(), nullable=True), sa.Column("motivo", sa.String(), nullable=False),
        sa.Column("aprovado_por", sa.String(), nullable=False), sa.Column("referencia_evidencia", sa.String(), nullable=True),
        sa.Column("referencia_legal", sa.String(), nullable=True),
        sa.Column("alterado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False), sa.Column("criado_por", sa.String(), nullable=True),
    )
    tabela = sa.table("periodo_status_tributario", *[sa.column(c) for c in PERIODO_2026])
    op.bulk_insert(tabela, [PERIODO_2026])


def downgrade() -> None:
    op.drop_table("periodo_status_tributario")
