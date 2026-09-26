"""Phase F: acesso do fornecedor (portal) e integração com a Business Network.

- `participante_sourcing`: e-mail, hash do link de acesso (único) e data;
- `proposta_sourcing.canal`: COMPRADOR (registrada) ou PORTAL (enviada pelo fornecedor);
- `esclarecimento_sourcing` (pergunta/resposta) e `anexo_sourcing` (evidência da
  proposta), com `lado` em CHECK e imutável (trigger da S3).

Revision ID: e1b3d5f7a9c0
Revises: d8a0c2e4f6b7
Create Date: 2026-09-26
"""

import sqlalchemy as sa

from alembic import op

revision = "e1b3d5f7a9c0"
down_revision = "d8a0c2e4f6b7"
branch_labels = None
depends_on = None

TABELAS = ("esclarecimento_sourcing", "anexo_sourcing")


def _base(nome: str):
    return [sa.Column("id", sa.Integer(), primary_key=True), sa.Column("tenant_id", sa.String(), nullable=False, index=True),
            sa.Column("lado", sa.String(), nullable=False),
            sa.CheckConstraint("lado IN ('SELL', 'BUY')", name=f"ck_{nome}_lado")]


def upgrade() -> None:
    op.add_column("participante_sourcing", sa.Column("email", sa.String(), nullable=True))
    op.add_column("participante_sourcing", sa.Column("token_hash", sa.String(), nullable=True))
    op.add_column("participante_sourcing", sa.Column("token_gerado_em", sa.DateTime(), nullable=True))
    op.create_index("uq_participante_sourcing_token_hash", "participante_sourcing", ["token_hash"], unique=True)
    op.add_column("proposta_sourcing", sa.Column("canal", sa.String(), nullable=False, server_default="COMPRADOR"))
    op.create_table(
        "esclarecimento_sourcing", *_base("esclarecimento_sourcing"),
        sa.Column("processo_id", sa.Integer(), sa.ForeignKey("processo_sourcing.id"), nullable=False, index=True),
        sa.Column("participante_id", sa.Integer(), sa.ForeignKey("participante_sourcing.id"), nullable=False, index=True),
        sa.Column("pergunta", sa.Text(), nullable=False),
        sa.Column("resposta", sa.Text(), nullable=True),
        sa.Column("revisado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("respondido_em", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "anexo_sourcing", *_base("anexo_sourcing"),
        sa.Column("proposta_id", sa.Integer(), sa.ForeignKey("proposta_sourcing.id"), nullable=False, index=True),
        sa.Column("nome_arquivo", sa.String(), nullable=False),
        sa.Column("tipo_mime", sa.String(), nullable=False),
        sa.Column("tamanho_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("conteudo", sa.LargeBinary(), nullable=False),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    dialeto = op.get_bind().dialect.name
    for tabela in TABELAS:
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
        op.drop_table(tabela)
    op.drop_column("proposta_sourcing", "canal")
    op.drop_index("uq_participante_sourcing_token_hash", table_name="participante_sourcing")
    for coluna in ("token_gerado_em", "token_hash", "email"):
        op.drop_column("participante_sourcing", coluna)
