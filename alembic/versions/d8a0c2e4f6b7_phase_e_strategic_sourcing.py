"""Phase E: Enterprise Strategic Sourcing (lado comprador privado).

Entidades que nascem com o primeiro fluxo que grava nelas (D-058/D-061):
`participante_sourcing`, `item_sourcing`, `proposta_sourcing`,
`proposta_item_sourcing` e `avaliacao_sourcing`, todas com `lado` em CHECK e
imutável por trigger (mesma função da S3). `peso` em `requisito_sourcing`
para critérios ponderados. Sem tabela de origem: são nativas do modelo
unificado.

Revision ID: d8a0c2e4f6b7
Revises: c6f8a0b2d4e5
Create Date: 2026-09-26
"""

import sqlalchemy as sa

from alembic import op

revision = "d8a0c2e4f6b7"
down_revision = "c6f8a0b2d4e5"
branch_labels = None
depends_on = None

TABELAS = ("participante_sourcing", "item_sourcing", "proposta_sourcing", "proposta_item_sourcing", "avaliacao_sourcing")


def _base(nome: str):
    return [sa.Column("id", sa.Integer(), primary_key=True), sa.Column("tenant_id", sa.String(), nullable=False, index=True),
            sa.Column("lado", sa.String(), nullable=False),
            sa.CheckConstraint("lado IN ('SELL', 'BUY')", name=f"ck_{nome}_lado")]


def upgrade() -> None:
    op.add_column("requisito_sourcing", sa.Column("peso", sa.Numeric(8, 2), nullable=True))
    op.create_table(
        "participante_sourcing", *_base("participante_sourcing"),
        sa.Column("processo_id", sa.Integer(), sa.ForeignKey("processo_sourcing.id"), nullable=False, index=True),
        sa.Column("fornecedor_id", sa.Integer(), nullable=True),
        sa.Column("empresa_rede_tenant_id", sa.String(), nullable=True),
        sa.Column("nome", sa.String(), nullable=False),
        sa.Column("cnpj", sa.String(), nullable=True),
        sa.Column("origem_descoberta", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "item_sourcing", *_base("item_sourcing"),
        sa.Column("processo_id", sa.Integer(), sa.ForeignKey("processo_sourcing.id"), nullable=False, index=True),
        sa.Column("descricao", sa.String(), nullable=False),
        sa.Column("quantidade", sa.Numeric(18, 4), nullable=False),
        sa.Column("unidade", sa.String(), nullable=True),
        sa.Column("especificacao", sa.Text(), nullable=True),
    )
    op.create_table(
        "proposta_sourcing", *_base("proposta_sourcing"),
        sa.Column("processo_id", sa.Integer(), sa.ForeignKey("processo_sourcing.id"), nullable=False),
        sa.Column("participante_id", sa.Integer(), sa.ForeignKey("participante_sourcing.id"), nullable=False, index=True),
        sa.Column("rodada", sa.Integer(), nullable=False),
        sa.Column("tipo", sa.String(), nullable=False),
        sa.Column("valor_total", sa.Numeric(18, 2), nullable=True),
        sa.Column("moeda", sa.String(), nullable=False),
        sa.Column("prazo_entrega_dias", sa.Integer(), nullable=True),
        sa.Column("condicoes_pagamento", sa.String(), nullable=True),
        sa.Column("impostos_inclusos", sa.Boolean(), nullable=True),
        sa.Column("validade", sa.Date(), nullable=True),
        sa.Column("observacoes", sa.Text(), nullable=True),
        sa.Column("criado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
        sa.Column("recebida_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_proposta_sourcing_processo_participante", "proposta_sourcing", ["processo_id", "participante_id"])
    op.create_table(
        "proposta_item_sourcing", *_base("proposta_item_sourcing"),
        sa.Column("proposta_id", sa.Integer(), sa.ForeignKey("proposta_sourcing.id"), nullable=False, index=True),
        sa.Column("item_id", sa.Integer(), sa.ForeignKey("item_sourcing.id"), nullable=False, index=True),
        sa.Column("preco_unitario", sa.Numeric(18, 4), nullable=False),
        sa.UniqueConstraint("proposta_id", "item_id", name="uq_proposta_item_sourcing"),
    )
    op.create_table(
        "avaliacao_sourcing", *_base("avaliacao_sourcing"),
        sa.Column("proposta_id", sa.Integer(), sa.ForeignKey("proposta_sourcing.id"), nullable=False, index=True),
        sa.Column("requisito_id", sa.Integer(), sa.ForeignKey("requisito_sourcing.id"), nullable=False, index=True),
        sa.Column("resposta", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("nota", sa.Numeric(5, 2), nullable=True),
        sa.Column("justificativa", sa.Text(), nullable=True),
        sa.Column("revisado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
        sa.Column("revisado_em", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("proposta_id", "requisito_id", name="uq_avaliacao_sourcing"),
    )
    dialeto = op.get_bind().dialect.name
    for tabela in TABELAS:  # a função `sourcing_lado_imutavel` (Postgres) já existe desde a S3
        if dialeto == "postgresql":
            op.execute(f"CREATE TRIGGER trg_{tabela}_lado_imutavel BEFORE UPDATE ON {tabela} "
                       f"FOR EACH ROW EXECUTE FUNCTION sourcing_lado_imutavel()")
        elif dialeto == "sqlite":
            op.execute(f"CREATE TRIGGER trg_{tabela}_lado_imutavel BEFORE UPDATE OF lado ON {tabela} "
                       f"WHEN NEW.lado <> OLD.lado BEGIN SELECT RAISE(ABORT, 'lado de {tabela} nao pode mudar'); END")


def downgrade() -> None:
    dialeto = op.get_bind().dialect.name
    for tabela in TABELAS:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{tabela}_lado_imutavel" + (f" ON {tabela}" if dialeto == "postgresql" else ""))
    for tabela in ("avaliacao_sourcing", "proposta_item_sourcing"):
        op.drop_table(tabela)
    op.drop_index("ix_proposta_sourcing_processo_participante", table_name="proposta_sourcing")
    for tabela in ("proposta_sourcing", "item_sourcing", "participante_sourcing"):
        op.drop_table(tabela)
    op.drop_column("requisito_sourcing", "peso")
