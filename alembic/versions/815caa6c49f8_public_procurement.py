"""Public Procurement (buy side) - Fase 10 do Master Prompt v4

Orgao, unidades, demandas, PCA, processos (workspace + timeline),
fornecedores (Supplier 360), contratos e eventos, pesquisa de precos e
documentos com proveniencia. Tudo CONFIDENTIAL do tenant comprador: a
barreira Buy/Sell impede leitura por Sell Side, Business Network ou
outro tenant.

Revision ID: 815caa6c49f8
Revises: 5ddf7b14a837
Create Date: 2026-09-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '815caa6c49f8'
down_revision: Union[str, Sequence[str], None] = '5ddf7b14a837'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "orgao_publico",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False, index=True),
        sa.Column("nome", sa.String(), nullable=False),
        sa.Column("cnpj", sa.String(), nullable=True),
        sa.Column("esfera", sa.String(), nullable=True),
        sa.Column("regime_juridico", sa.String(), nullable=True),
        sa.Column("parametros", sa.JSON(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "unidade_compras",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False, index=True),
        sa.Column("orgao_id", sa.Integer(), sa.ForeignKey("orgao_publico.id"), nullable=False),
        sa.Column("nome", sa.String(), nullable=False),
        sa.Column("codigo", sa.String(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "plano_contratacao",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False, index=True),
        sa.Column("orgao_id", sa.Integer(), sa.ForeignKey("orgao_publico.id"), nullable=False),
        sa.Column("ano", sa.Integer(), nullable=False),
        sa.Column("nome", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("aprovado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
        sa.Column("aprovado_em", sa.DateTime(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "item_pca",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False, index=True),
        sa.Column("plano_id", sa.Integer(), sa.ForeignKey("plano_contratacao.id"), nullable=False),
        sa.Column("descricao", sa.String(), nullable=False),
        sa.Column("categoria", sa.String(), nullable=True),
        sa.Column("valor_estimado", sa.Float(), nullable=True),
        sa.Column("data_prevista", sa.Date(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "demanda_compra",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False, index=True),
        sa.Column("unidade_id", sa.Integer(), sa.ForeignKey("unidade_compras.id"), nullable=False),
        sa.Column("solicitante_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
        sa.Column("necessidade", sa.Text(), nullable=False),
        sa.Column("justificativa", sa.Text(), nullable=True),
        sa.Column("categoria", sa.String(), nullable=True),
        sa.Column("valor_estimado", sa.Float(), nullable=True),
        sa.Column("prioridade", sa.String(), nullable=True),
        sa.Column("data_necessaria", sa.Date(), nullable=True),
        sa.Column("referencia_orcamentaria", sa.String(), nullable=True),
        sa.Column("item_pca_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("aprovado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
        sa.Column("aprovado_em", sa.DateTime(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "processo_contratacao",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False, index=True),
        sa.Column("orgao_id", sa.Integer(), sa.ForeignKey("orgao_publico.id"), nullable=False),
        sa.Column("unidade_id", sa.Integer(), sa.ForeignKey("unidade_compras.id"), nullable=True),
        sa.Column("item_pca_id", sa.Integer(), sa.ForeignKey("item_pca.id"), nullable=True),
        sa.Column("numero", sa.String(), nullable=True),
        sa.Column("objeto", sa.Text(), nullable=False),
        sa.Column("modalidade", sa.String(), nullable=True),
        sa.Column("categoria", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("valor_estimado", sa.Float(), nullable=True),
        sa.Column("valor_sigiloso", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("prazo_previsto", sa.Date(), nullable=True),
        sa.Column("publicado_em", sa.DateTime(), nullable=True),
        sa.Column("responsavel_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
        sa.Column("demanda_ids", sa.JSON(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "evento_processo",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False, index=True),
        sa.Column("processo_id", sa.Integer(), sa.ForeignKey("processo_contratacao.id"), nullable=False),
        sa.Column("tipo", sa.String(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("prazo", sa.Date(), nullable=True),
        sa.Column("responsavel_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
        sa.Column("criado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
        sa.Column("concluido_em", sa.DateTime(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "fornecedor_compras",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False, index=True),
        sa.Column("cnpj", sa.String(), nullable=True),
        sa.Column("razao_social", sa.String(), nullable=False),
        sa.Column("categorias", sa.JSON(), nullable=True),
        sa.Column("dados_oficiais", sa.JSON(), nullable=True),
        sa.Column("dados_internos", sa.JSON(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "contrato_compra",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False, index=True),
        sa.Column("orgao_id", sa.Integer(), sa.ForeignKey("orgao_publico.id"), nullable=False),
        sa.Column("processo_id", sa.Integer(), sa.ForeignKey("processo_contratacao.id"), nullable=True),
        sa.Column("fornecedor_id", sa.Integer(), sa.ForeignKey("fornecedor_compras.id"), nullable=False),
        sa.Column("numero", sa.String(), nullable=True),
        sa.Column("objeto", sa.Text(), nullable=False),
        sa.Column("categoria", sa.String(), nullable=True),
        sa.Column("valor_inicial", sa.Float(), nullable=True),
        sa.Column("valor_atual", sa.Float(), nullable=True),
        sa.Column("vigencia_inicio", sa.Date(), nullable=True),
        sa.Column("vigencia_fim", sa.Date(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("necessidade_continuada", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sla", sa.Text(), nullable=True),
        sa.Column("garantia", sa.String(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "evento_contrato_compra",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False, index=True),
        sa.Column("fornecedor_id", sa.Integer(), sa.ForeignKey("fornecedor_compras.id"), nullable=False),
        sa.Column("contrato_id", sa.Integer(), sa.ForeignKey("contrato_compra.id"), nullable=True),
        sa.Column("tipo", sa.String(), nullable=False),
        sa.Column("descricao", sa.Text(), nullable=True),
        sa.Column("valor", sa.Float(), nullable=True),
        sa.Column("nota", sa.Float(), nullable=True),
        sa.Column("data", sa.Date(), nullable=True),
        sa.Column("criado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "documento_compras",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False, index=True),
        sa.Column("processo_id", sa.Integer(), sa.ForeignKey("processo_contratacao.id"), nullable=True),
        sa.Column("contrato_id", sa.Integer(), sa.ForeignKey("contrato_compra.id"), nullable=True),
        sa.Column("tipo", sa.String(), nullable=False),
        sa.Column("nome_arquivo", sa.String(), nullable=False),
        sa.Column("tipo_mime", sa.String(), nullable=False),
        sa.Column("tamanho_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(), nullable=False),
        sa.Column("conteudo", sa.LargeBinary(), nullable=True),
        sa.Column("paginas_texto", sa.JSON(), nullable=True),
        sa.Column("paginas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fonte", sa.String(), nullable=False),
        sa.Column("fonte_url", sa.String(), nullable=True),
        sa.Column("classificacao", sa.String(), nullable=False),
        sa.Column("achados", sa.JSON(), nullable=True),
        sa.Column("status_analise", sa.String(), nullable=False),
        sa.Column("enviado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "pesquisa_preco",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False, index=True),
        sa.Column("processo_id", sa.Integer(), sa.ForeignKey("processo_contratacao.id"), nullable=False),
        sa.Column("item_descricao", sa.String(), nullable=False),
        sa.Column("unidade", sa.String(), nullable=True),
        sa.Column("preco_unitario", sa.Float(), nullable=False),
        sa.Column("fonte_tipo", sa.String(), nullable=False),
        sa.Column("fonte_descricao", sa.String(), nullable=False),
        sa.Column("data_coleta", sa.Date(), nullable=True),
        sa.Column("documento_id", sa.Integer(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_unidade_compras_orgao_id", "unidade_compras", ["orgao_id"])
    op.create_index("ix_plano_contratacao_orgao_id", "plano_contratacao", ["orgao_id"])
    op.create_index("ix_item_pca_plano_id", "item_pca", ["plano_id"])
    op.create_index("ix_processo_contratacao_orgao_id", "processo_contratacao", ["orgao_id"])
    op.create_index("ix_evento_processo_processo_id", "evento_processo", ["processo_id"])
    op.create_index("ix_contrato_compra_orgao_id", "contrato_compra", ["orgao_id"])
    op.create_index("ix_contrato_compra_fornecedor_id", "contrato_compra", ["fornecedor_id"])
    op.create_index("ix_evento_contrato_compra_fornecedor_id", "evento_contrato_compra", ["fornecedor_id"])
    op.create_index("ix_pesquisa_preco_processo_id", "pesquisa_preco", ["processo_id"])


def downgrade() -> None:
    op.drop_table("pesquisa_preco")
    op.drop_table("documento_compras")
    op.drop_table("evento_contrato_compra")
    op.drop_table("contrato_compra")
    op.drop_table("fornecedor_compras")
    op.drop_table("evento_processo")
    op.drop_table("processo_contratacao")
    op.drop_table("demanda_compra")
    op.drop_table("item_pca")
    op.drop_table("plano_contratacao")
    op.drop_table("unidade_compras")
    op.drop_table("orgao_publico")
