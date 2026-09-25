"""AI FinOps e creditos - Fase 5 do Master Prompt v4

Tabela de custo por modelo (custo do PROVEDOR, nao preco ao cliente),
politica de creditos (semeada como PENDING_DEFINITION: a taxa e decisao
do Product Owner), carteira + extrato por tenant, orcamentos/quotas e
colunas de custo/credito no ledger.

Revision ID: f892ebf6e6f9
Revises: b53c1ac42468
Create Date: 2026-09-25

"""
from datetime import date
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f892ebf6e6f9'
down_revision: Union[str, Sequence[str], None] = 'b53c1ac42468'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FONTE = (
    "Anthropic API pricing (USD/MTok) conforme tabela de modelos da skill claude-api, cache 2026-06-24. "
    "Escrita de cache = 1,25x entrada (TTL 5 min); leitura = 0,1x entrada, salvo valor publicado."
)
# (modelo, entrada, saida, cache_escrita, cache_leitura)
_PRECOS = [
    ("claude-haiku-4-5", 1.0, 5.0, 1.25, 0.10),
    ("claude-sonnet-5", 2.0, 10.0, 2.50, 0.20),
    ("claude-sonnet-4-6", 3.0, 15.0, 3.75, 0.30),
    ("claude-opus-5", 5.0, 25.0, 6.25, 0.50),
    ("claude-opus-5-5", 4.0, 20.0, 5.00, 0.20),
    ("claude-opus-4-8", 5.0, 25.0, 6.25, 0.50),
]


def upgrade() -> None:
    preco = op.create_table(
        'preco_modelo_ia',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(), nullable=False),
        sa.Column('modelo', sa.String(), nullable=False),
        sa.Column('vigente_desde', sa.Date(), nullable=False),
        sa.Column('entrada_usd_mtok', sa.Numeric(12, 6), nullable=False),
        sa.Column('saida_usd_mtok', sa.Numeric(12, 6), nullable=False),
        sa.Column('cache_escrita_usd_mtok', sa.Numeric(12, 6), nullable=False),
        sa.Column('cache_leitura_usd_mtok', sa.Numeric(12, 6), nullable=False),
        sa.Column('fonte', sa.String(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider', 'modelo', 'vigente_desde'),
    )
    op.create_index('ix_preco_modelo_ia_modelo', 'preco_modelo_ia', ['modelo'])
    op.bulk_insert(preco, [
        {"provider": "anthropic", "modelo": m, "vigente_desde": date(2026, 6, 24), "entrada_usd_mtok": e,
         "saida_usd_mtok": s, "cache_escrita_usd_mtok": cw, "cache_leitura_usd_mtok": cr, "fonte": _FONTE}
        for m, e, s, cw, cr in _PRECOS
    ])

    politica = op.create_table(
        'politica_creditos_ia',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='PENDING_DEFINITION'),
        sa.Column('creditos_por_usd', sa.Numeric(14, 4), nullable=True),
        sa.Column('permite_excedente', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('exige_saldo', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('observacao', sa.String(), nullable=True),
        sa.Column('vigente_desde', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.bulk_insert(politica, [{
        "status": "PENDING_DEFINITION", "creditos_por_usd": None, "permite_excedente": False, "exige_saldo": False,
        "observacao": "Taxa de conversao a definir pelo Product Owner (Master Prompt secao 55). Custo ja e medido.",
    }])

    op.create_table(
        'carteira_creditos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('saldo', sa.Numeric(18, 4), nullable=False, server_default='0'),
        sa.Column('atualizado_em', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('tenant_id'),
    )

    with op.batch_alter_table('registro_uso_ia') as batch:
        batch.add_column(sa.Column('custo_usd', sa.Numeric(18, 8), nullable=True))
        batch.add_column(sa.Column('preco_id', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('creditos_consumidos', sa.Numeric(18, 4), nullable=True))

    op.create_table(
        'movimento_credito',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('tipo', sa.String(), nullable=False),
        sa.Column('quantidade', sa.Numeric(18, 4), nullable=False),
        sa.Column('saldo_apos', sa.Numeric(18, 4), nullable=False),
        sa.Column('registro_uso_ia_id', sa.Integer(), sa.ForeignKey('registro_uso_ia.id'), nullable=True),
        sa.Column('descricao', sa.String(), nullable=True),
        sa.Column('ator_id', sa.String(), nullable=True),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_movimento_credito_tenant_id', 'movimento_credito', ['tenant_id'])
    op.create_index('ix_movimento_credito_registro_uso_ia_id', 'movimento_credito', ['registro_uso_ia_id'])

    op.create_table(
        'orcamento_ia',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('tenant_id', sa.String(), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('escopo', sa.String(), nullable=False, server_default='tenant'),
        sa.Column('alvo', sa.String(), nullable=True),
        sa.Column('limite_custo_usd', sa.Numeric(14, 4), nullable=True),
        sa.Column('limite_chamadas', sa.Integer(), nullable=True),
        sa.Column('acao', sa.String(), nullable=False, server_default='ALERTAR'),
        sa.Column('percentual_alerta', sa.Integer(), nullable=False, server_default='80'),
        sa.Column('ativo', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('criado_em', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_orcamento_ia_tenant_id', 'orcamento_ia', ['tenant_id'])


def downgrade() -> None:
    op.drop_index('ix_orcamento_ia_tenant_id', table_name='orcamento_ia')
    op.drop_table('orcamento_ia')
    op.drop_index('ix_movimento_credito_registro_uso_ia_id', table_name='movimento_credito')
    op.drop_index('ix_movimento_credito_tenant_id', table_name='movimento_credito')
    op.drop_table('movimento_credito')
    with op.batch_alter_table('registro_uso_ia') as batch:
        batch.drop_column('creditos_consumidos')
        batch.drop_column('preco_id')
        batch.drop_column('custo_usd')
    op.drop_table('carteira_creditos')
    op.drop_table('politica_creditos_ia')
    op.drop_index('ix_preco_modelo_ia_modelo', table_name='preco_modelo_ia')
    op.drop_table('preco_modelo_ia')
