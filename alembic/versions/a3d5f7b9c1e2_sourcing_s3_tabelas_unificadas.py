"""Sourcing S3 (expand): tabelas unificadas de Strategic Sourcing & Bids.

Seis tabelas com `lado` (SELL|BUY) em CHECK e imutável por trigger, mapa
de origem (`origem_tabela`, `origem_id`) único. As tabelas antigas continuam
a fonte da verdade; o conteúdo chega por espelho (eventos do ORM) e pelo
backfill idempotente em lotes (`/cron/sourcing-sincronizar`). Sem cópia de
blobs: arquivo e texto continuam na origem até a S6.

Revision ID: a3d5f7b9c1e2
Revises: e7b3c1a9f5d2
Create Date: 2026-09-26
"""

import sqlalchemy as sa

from alembic import op

revision = "a3d5f7b9c1e2"
down_revision = "e7b3c1a9f5d2"
branch_labels = None
depends_on = None

TABELAS = ("processo_sourcing", "contrato_sourcing", "documento_sourcing", "requisito_sourcing", "evento_sourcing",
           "evento_contrato_sourcing")


def _comuns():
    return [sa.Column("origem_tabela", sa.String(), nullable=False), sa.Column("origem_id", sa.Integer(), nullable=False),
            sa.Column("criado_em", sa.DateTime(), nullable=True),
            sa.Column("espelhado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False)]


def upgrade() -> None:
    op.create_table(
        "processo_sourcing",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False, index=True),
        sa.Column("lado", sa.String(), nullable=False),
        sa.Column("segmento", sa.String(), nullable=False),
        sa.Column("tipo_processo", sa.String(), nullable=False),
        sa.Column("titulo", sa.String(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("emissor_nome", sa.String(), nullable=True),
        sa.Column("emissor_cnpj", sa.String(), nullable=True),
        sa.Column("conta_id", sa.Integer(), sa.ForeignKey("conta.id"), nullable=True, index=True),
        sa.Column("oferta_id", sa.Integer(), sa.ForeignKey("oferta.id"), nullable=True, index=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("visibilidade", sa.String(), nullable=False),
        sa.Column("classificacao", sa.String(), nullable=False),
        sa.Column("ruleset", sa.String(), nullable=True),
        sa.Column("workflow", sa.String(), nullable=False),
        sa.Column("publicado_em", sa.DateTime(), nullable=True),
        sa.Column("prazo", sa.DateTime(), nullable=True),
        sa.Column("valor_estimado", sa.Numeric(18, 2), nullable=True),
        sa.Column("moeda", sa.String(), nullable=False),
        sa.Column("valor_sigiloso", sa.Boolean(), nullable=False),
        sa.Column("responsavel_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
        sa.Column("fonte", sa.String(), nullable=False),
        sa.Column("fonte_id_externo", sa.String(), nullable=True),
        sa.Column("fonte_url", sa.String(), nullable=True),
        sa.Column("metadados", sa.JSON(), nullable=True),
        *_comuns(),
        sa.UniqueConstraint("origem_tabela", "origem_id", name="uq_processo_sourcing_origem"),
        sa.CheckConstraint("lado IN ('SELL', 'BUY')", name="ck_processo_sourcing_lado"),
        sa.CheckConstraint("segmento IN ('PUBLIC', 'ENTERPRISE')", name="ck_processo_sourcing_segmento"),
    )
    op.create_index("ix_processo_sourcing_tenant_lado_status", "processo_sourcing", ["tenant_id", "lado", "status"])
    op.create_index("ix_processo_sourcing_tenant_lado_prazo", "processo_sourcing", ["tenant_id", "lado", "prazo"])

    op.create_table(
        "contrato_sourcing",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False, index=True),
        sa.Column("lado", sa.String(), nullable=False),
        sa.Column("processo_id", sa.Integer(), sa.ForeignKey("processo_sourcing.id"), nullable=True, index=True),
        sa.Column("contraparte_nome", sa.String(), nullable=True),
        sa.Column("conta_id", sa.Integer(), sa.ForeignKey("conta.id"), nullable=True, index=True),
        sa.Column("fornecedor_id", sa.Integer(), nullable=True),
        sa.Column("numero", sa.String(), nullable=True),
        sa.Column("objeto", sa.Text(), nullable=False),
        sa.Column("categoria", sa.String(), nullable=True),
        sa.Column("valor_inicial", sa.Numeric(18, 2), nullable=True),
        sa.Column("valor_atual", sa.Numeric(18, 2), nullable=True),
        sa.Column("vigencia_inicio", sa.Date(), nullable=True),
        sa.Column("vigencia_fim", sa.Date(), nullable=True),
        sa.Column("renovavel", sa.Boolean(), nullable=True),
        sa.Column("necessidade_continuada", sa.Boolean(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("sla", sa.Text(), nullable=True),
        sa.Column("garantia", sa.String(), nullable=True),
        sa.Column("metadados", sa.JSON(), nullable=True),
        *_comuns(),
        sa.UniqueConstraint("origem_tabela", "origem_id", name="uq_contrato_sourcing_origem"),
        sa.CheckConstraint("lado IN ('SELL', 'BUY')", name="ck_contrato_sourcing_lado"),
    )
    op.create_index("ix_contrato_sourcing_tenant_lado_status", "contrato_sourcing", ["tenant_id", "lado", "status"])

    op.create_table(
        "documento_sourcing",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False, index=True),
        sa.Column("lado", sa.String(), nullable=False),
        sa.Column("processo_id", sa.Integer(), sa.ForeignKey("processo_sourcing.id"), nullable=True, index=True),
        sa.Column("contrato_id", sa.Integer(), sa.ForeignKey("contrato_sourcing.id"), nullable=True, index=True),
        sa.Column("tipo_documento", sa.String(), nullable=False),
        sa.Column("nome_arquivo", sa.String(), nullable=False),
        sa.Column("tipo_mime", sa.String(), nullable=False),
        sa.Column("tamanho_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("paginas", sa.Integer(), nullable=False),
        sa.Column("fonte", sa.String(), nullable=False),
        sa.Column("fonte_url", sa.String(), nullable=True),
        sa.Column("classificacao", sa.String(), nullable=False),
        sa.Column("versao", sa.Integer(), nullable=False),
        sa.Column("status_extracao", sa.String(), nullable=False),
        sa.Column("analisado_em", sa.DateTime(), nullable=True),
        sa.Column("enviado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
        *_comuns(),
        sa.UniqueConstraint("origem_tabela", "origem_id", name="uq_documento_sourcing_origem"),
        sa.CheckConstraint("lado IN ('SELL', 'BUY')", name="ck_documento_sourcing_lado"),
    )

    op.create_table(
        "requisito_sourcing",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False, index=True),
        sa.Column("lado", sa.String(), nullable=False),
        sa.Column("processo_id", sa.Integer(), sa.ForeignKey("processo_sourcing.id"), nullable=True, index=True),
        sa.Column("documento_id", sa.Integer(), sa.ForeignKey("documento_sourcing.id"), nullable=True, index=True),
        sa.Column("categoria", sa.String(), nullable=False),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column("fonte", sa.String(), nullable=False),
        sa.Column("pagina", sa.Integer(), nullable=True),
        sa.Column("clausula", sa.String(), nullable=True),
        sa.Column("trecho", sa.Text(), nullable=True),
        sa.Column("confianca", sa.String(), nullable=False),
        sa.Column("status_revisao", sa.String(), nullable=False),
        sa.Column("conformidade_manual", sa.String(), nullable=True),
        sa.Column("justificativa_manual", sa.String(), nullable=True),
        sa.Column("revisado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
        sa.Column("revisado_em", sa.DateTime(), nullable=True),
        sa.Column("correlation_id", sa.String(), nullable=True),
        sa.Column("origem_tabela", sa.String(), nullable=False),
        sa.Column("origem_id", sa.Integer(), nullable=False),
        sa.Column("origem_indice", sa.Integer(), nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=True),
        sa.Column("espelhado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("origem_tabela", "origem_id", "origem_indice", name="uq_requisito_sourcing_origem"),
        sa.CheckConstraint("lado IN ('SELL', 'BUY')", name="ck_requisito_sourcing_lado"),
    )

    op.create_table(
        "evento_sourcing",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False, index=True),
        sa.Column("lado", sa.String(), nullable=False),
        sa.Column("processo_id", sa.Integer(), sa.ForeignKey("processo_sourcing.id"), nullable=True, index=True),
        sa.Column("tipo", sa.String(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("prazo", sa.Date(), nullable=True),
        sa.Column("responsavel_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
        sa.Column("criado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
        sa.Column("concluido_em", sa.DateTime(), nullable=True),
        *_comuns(),
        sa.UniqueConstraint("origem_tabela", "origem_id", name="uq_evento_sourcing_origem"),
        sa.CheckConstraint("lado IN ('SELL', 'BUY')", name="ck_evento_sourcing_lado"),
    )

    op.create_table(
        "evento_contrato_sourcing",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False, index=True),
        sa.Column("lado", sa.String(), nullable=False),
        sa.Column("contrato_id", sa.Integer(), sa.ForeignKey("contrato_sourcing.id"), nullable=True, index=True),
        sa.Column("fornecedor_id", sa.Integer(), nullable=True),
        sa.Column("tipo", sa.String(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("valor", sa.Numeric(18, 2), nullable=True),
        sa.Column("nota", sa.Numeric(6, 2), nullable=True),
        sa.Column("data", sa.Date(), nullable=True),
        sa.Column("criado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
        *_comuns(),
        sa.UniqueConstraint("origem_tabela", "origem_id", name="uq_evento_contrato_sourcing_origem"),
        sa.CheckConstraint("lado IN ('SELL', 'BUY')", name="ck_evento_contrato_sourcing_lado"),
    )

    # Lado imutável também por SQL direto (barreira Buy/Sell, D-055 §2.3).
    dialeto = op.get_bind().dialect.name
    if dialeto == "postgresql":
        op.execute("""
            CREATE OR REPLACE FUNCTION sourcing_lado_imutavel() RETURNS trigger AS $$
            BEGIN
                IF NEW.lado IS DISTINCT FROM OLD.lado THEN
                    RAISE EXCEPTION USING MESSAGE = 'lado de ' || TG_TABLE_NAME || ' nao pode mudar';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """)
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
    if dialeto == "postgresql":
        op.execute("DROP FUNCTION IF EXISTS sourcing_lado_imutavel()")
    for tabela in ("evento_contrato_sourcing", "evento_sourcing", "requisito_sourcing", "documento_sourcing"):
        op.drop_table(tabela)
    op.drop_index("ix_contrato_sourcing_tenant_lado_status", table_name="contrato_sourcing")
    op.drop_table("contrato_sourcing")
    op.drop_index("ix_processo_sourcing_tenant_lado_prazo", table_name="processo_sourcing")
    op.drop_index("ix_processo_sourcing_tenant_lado_status", table_name="processo_sourcing")
    op.drop_table("processo_sourcing")
