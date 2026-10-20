"""Documentos de Relações com Investidores e indicadores extraídos (V5.2.1, Fase 5).

Não guarda o arquivo (só hash, metadados e evidências). Downgrade: remove as duas tabelas e, com elas, documentos e indicadores de RI já extraídos
(o PDF pode ser reenviado; indicadores conferidos manualmente se perdem).

Revision ID: f3d5a7c9e1b4
Revises: e2c4f6a8b0d3
Create Date: 2026-10-20
"""
import sqlalchemy as sa
from alembic import op

revision = "f3d5a7c9e1b4"
down_revision = "e2c4f6a8b0d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "documento_ri",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("conta_id", sa.Integer(), sa.ForeignKey("conta.id"), nullable=False),
        sa.Column("origem", sa.String(), nullable=False),
        sa.Column("nome_arquivo", sa.String(), nullable=False),
        sa.Column("url_fonte", sa.String(), nullable=True),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("tamanho_bytes", sa.Integer(), nullable=False),
        sa.Column("paginas", sa.Integer(), nullable=True),
        sa.Column("tipo_documento", sa.String(), nullable=False, server_default="outro"),
        sa.Column("titulo", sa.String(), nullable=True),
        sa.Column("data_publicacao", sa.Date(), nullable=True),
        sa.Column("estado", sa.String(), nullable=False),
        sa.Column("erro", sa.Text(), nullable=True),
        sa.Column("avisos", sa.JSON(), nullable=False),
        sa.Column("sinais", sa.JSON(), nullable=False),
        sa.Column("criado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("processado_em", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("tenant_id", "conta_id", "sha256", name="uq_documento_ri_tenant_conta_sha"),
    )
    op.create_index("ix_documento_ri_tenant_id", "documento_ri", ["tenant_id"])
    op.create_index("ix_documento_ri_conta_id", "documento_ri", ["conta_id"])
    op.create_table(
        "indicador_ri",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("conta_id", sa.Integer(), sa.ForeignKey("conta.id"), nullable=False),
        sa.Column("documento_id", sa.Integer(), sa.ForeignKey("documento_ri.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nome", sa.String(), nullable=False),
        sa.Column("tipo", sa.String(), nullable=False, server_default="publicado"),
        sa.Column("valor", sa.Float(), nullable=False),
        sa.Column("moeda", sa.String(), nullable=False),
        sa.Column("escala", sa.String(), nullable=False),
        sa.Column("valor_original", sa.String(), nullable=False),
        sa.Column("periodo", sa.String(), nullable=True),
        sa.Column("pagina", sa.Integer(), nullable=True),
        sa.Column("trecho", sa.Text(), nullable=False),
        sa.Column("metodo_extracao", sa.String(), nullable=False),
        sa.Column("confianca", sa.String(), nullable=False),
        sa.Column("estado_validacao", sa.String(), nullable=False, server_default="extraido_automaticamente"),
        sa.Column("formula", sa.String(), nullable=True),
        sa.Column("origens", sa.JSON(), nullable=False),
        sa.Column("observacao", sa.String(), nullable=True),
        sa.Column("coletado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_indicador_ri_tenant_id", "indicador_ri", ["tenant_id"])
    op.create_index("ix_indicador_ri_conta_id", "indicador_ri", ["conta_id"])
    op.create_index("ix_indicador_ri_documento_id", "indicador_ri", ["documento_id"])


def downgrade() -> None:
    op.drop_index("ix_indicador_ri_documento_id", table_name="indicador_ri")
    op.drop_index("ix_indicador_ri_conta_id", table_name="indicador_ri")
    op.drop_index("ix_indicador_ri_tenant_id", table_name="indicador_ri")
    op.drop_table("indicador_ri")
    op.drop_index("ix_documento_ri_conta_id", table_name="documento_ri")
    op.drop_index("ix_documento_ri_tenant_id", table_name="documento_ri")
    op.drop_table("documento_ri")
