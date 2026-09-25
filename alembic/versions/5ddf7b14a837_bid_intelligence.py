"""Bid Intelligence (sell side) - Fase 9 do Master Prompt v4

Licitacoes/RFPs do tenant (vendedor), documentos com texto por pagina e
hash (proveniencia), requisitos extraidos com evidencia literal, cofre de
documentos com validade, decisoes Go/No-Go (humanas, com a recomendacao
que as precedeu) e contratos ganhos.

Revision ID: 5ddf7b14a837
Revises: 6a6ea43222b8
Create Date: 2026-09-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '5ddf7b14a837'
down_revision: Union[str, Sequence[str], None] = '6a6ea43222b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "licitacao",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False, index=True),
        sa.Column("titulo", sa.String(), nullable=False),
        sa.Column("objeto", sa.Text(), nullable=True),
        sa.Column("orgao_nome", sa.String(), nullable=True),
        sa.Column("orgao_cnpj", sa.String(), nullable=True),
        sa.Column("conta_id", sa.Integer(), sa.ForeignKey("conta.id"), nullable=True),
        sa.Column("oferta_id", sa.Integer(), sa.ForeignKey("oferta.id"), nullable=True),
        sa.Column("modalidade", sa.String(), nullable=False),
        sa.Column("fonte", sa.String(), nullable=False),
        sa.Column("fonte_id_externo", sa.String(), nullable=True),
        sa.Column("fonte_url", sa.String(), nullable=True),
        sa.Column("data_publicacao", sa.DateTime(), nullable=True),
        sa.Column("prazo_proposta", sa.DateTime(), nullable=True),
        sa.Column("prazo_esclarecimento", sa.DateTime(), nullable=True),
        sa.Column("valor_estimado", sa.Float(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("responsavel_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
        sa.Column("concorrentes", sa.JSON(), nullable=True),
        sa.Column("parceiros", sa.JSON(), nullable=True),
        sa.Column("vencedor", sa.String(), nullable=True),
        sa.Column("valor_proposta", sa.Float(), nullable=True),
        sa.Column("motivo_resultado", sa.String(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_licitacao_fonte_externa_unica", "licitacao", ["tenant_id", "fonte", "fonte_id_externo"], unique=True,
        postgresql_where=sa.text("fonte_id_externo IS NOT NULL"), sqlite_where=sa.text("fonte_id_externo IS NOT NULL"),
    )

    op.create_table(
        "documento_licitacao",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False, index=True),
        sa.Column("licitacao_id", sa.Integer(), sa.ForeignKey("licitacao.id"), nullable=False, index=True),
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
        sa.Column("status_analise", sa.String(), nullable=False),
        sa.Column("analisado_em", sa.DateTime(), nullable=True),
        sa.Column("enviado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("licitacao_id", "sha256", name="uq_documento_licitacao_hash"),
    )

    op.create_table(
        "requisito_licitacao",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False, index=True),
        sa.Column("licitacao_id", sa.Integer(), sa.ForeignKey("licitacao.id"), nullable=False, index=True),
        sa.Column("documento_id", sa.Integer(), sa.ForeignKey("documento_licitacao.id"), nullable=True),
        sa.Column("categoria", sa.String(), nullable=False),
        sa.Column("descricao", sa.String(), nullable=False),
        sa.Column("evidencia", sa.Text(), nullable=True),
        sa.Column("pagina", sa.Integer(), nullable=True),
        sa.Column("clausula", sa.String(), nullable=True),
        sa.Column("origem", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("conformidade_manual", sa.String(), nullable=True),
        sa.Column("justificativa_manual", sa.String(), nullable=True),
        sa.Column("revisado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
        sa.Column("revisado_em", sa.DateTime(), nullable=True),
        sa.Column("correlation_id", sa.String(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "documento_cofre",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False, index=True),
        sa.Column("tipo", sa.String(), nullable=False),
        sa.Column("nome", sa.String(), nullable=False),
        sa.Column("emissor", sa.String(), nullable=True),
        sa.Column("escopo", sa.Text(), nullable=True),
        sa.Column("palavras_chave", sa.JSON(), nullable=True),
        sa.Column("valido_desde", sa.Date(), nullable=True),
        sa.Column("valido_ate", sa.Date(), nullable=True),
        sa.Column("nome_arquivo", sa.String(), nullable=True),
        sa.Column("tipo_mime", sa.String(), nullable=True),
        sa.Column("tamanho_bytes", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(), nullable=True),
        sa.Column("conteudo", sa.LargeBinary(), nullable=True),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("enviado_por_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "decisao_go_no_go",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False, index=True),
        sa.Column("licitacao_id", sa.Integer(), sa.ForeignKey("licitacao.id"), nullable=False, index=True),
        sa.Column("recomendacao", sa.String(), nullable=False),
        sa.Column("fatores", sa.JSON(), nullable=False),
        sa.Column("decisao", sa.String(), nullable=False),
        sa.Column("justificativa", sa.String(), nullable=True),
        sa.Column("decidido_por_usuario_id", sa.Integer(), sa.ForeignKey("usuario.id"), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "contrato_venda_publica",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False, index=True),
        sa.Column("licitacao_id", sa.Integer(), sa.ForeignKey("licitacao.id"), nullable=True),
        sa.Column("conta_id", sa.Integer(), sa.ForeignKey("conta.id"), nullable=True),
        sa.Column("orgao_nome", sa.String(), nullable=True),
        sa.Column("numero", sa.String(), nullable=True),
        sa.Column("objeto", sa.String(), nullable=False),
        sa.Column("valor", sa.Float(), nullable=True),
        sa.Column("vigencia_inicio", sa.Date(), nullable=True),
        sa.Column("vigencia_fim", sa.Date(), nullable=True),
        sa.Column("renovavel", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("contrato_venda_publica")
    op.drop_table("decisao_go_no_go")
    op.drop_table("documento_cofre")
    op.drop_table("requisito_licitacao")
    op.drop_table("documento_licitacao")
    op.drop_index("ix_licitacao_fonte_externa_unica", table_name="licitacao")
    op.drop_table("licitacao")
