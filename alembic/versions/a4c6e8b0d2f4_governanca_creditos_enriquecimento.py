"""Governança de créditos de enriquecimento (pesquisa de decisores): configuração versionada e aprovada, razão append-only, pesquisa, orçamento
global, política do provedor (tarifas, custo, markup, preço), lotes de compra e leituras de uso do provedor.

Só cria tabelas novas: nenhuma linha existente é tocada e nenhum saldo é inventado. A única linha inserida é o lote de compra informado pelo
PO (R$ 269,94 por 400 créditos Lusha), como histórico de custo; ele NÃO libera nada: sem plano, política e orçamento global aprovados a pesquisa
de decisores continua bloqueada.

Downgrade: remove as tabelas e, com elas, configuração, razão, pesquisas, lotes e leituras de uso de enriquecimento. Os decisores já gravados
e os créditos/lotes de IA não são tocados. O razão e os lotes são histórico financeiro: faça cópia antes de reverter em ambiente com uso.

Revision ID: a4c6e8b0d2f4
Revises: f3d5a7c9e1b4
Create Date: 2026-10-21
"""
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from alembic import op

revision = "a4c6e8b0d2f4"
down_revision = "f3d5a7c9e1b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "enriquecimento_carteira",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False, unique=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "enriquecimento_config_plano",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("plano_id", sa.Integer(), sa.ForeignKey("plano.id"), nullable=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=True),
        sa.Column("versao", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("franquia_creditos", sa.Integer(), nullable=True),
        sa.Column("periodicidade", sa.String(), nullable=True),
        sa.Column("decisores_por_empresa_padrao", sa.Integer(), nullable=True),
        sa.Column("decisores_por_empresa_max", sa.Integer(), nullable=True),
        sa.Column("itens_por_lote_max", sa.Integer(), nullable=True),
        sa.Column("limite_periodo_creditos", sa.Integer(), nullable=True),
        sa.Column("motivo", sa.String(), nullable=True),
        sa.Column("criado_por", sa.String(), nullable=True),
        sa.Column("aprovado_por", sa.String(), nullable=True),
        sa.Column("aprovado_em", sa.DateTime(), nullable=True),
        sa.Column("valido_de", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("valido_ate", sa.DateTime(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("plano_id", "versao", name="uq_enriq_config_plano_versao"),
        sa.UniqueConstraint("tenant_id", "versao", name="uq_enriq_config_tenant_versao"),
    )
    op.create_index("ix_enriquecimento_config_plano_plano_id", "enriquecimento_config_plano", ["plano_id"])
    op.create_index("ix_enriquecimento_config_plano_tenant_id", "enriquecimento_config_plano", ["tenant_id"])
    op.create_table(
        "enriquecimento_orcamento_global",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provedor", sa.String(), nullable=False),
        sa.Column("versao", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("limite_creditos", sa.Integer(), nullable=True),
        sa.Column("alerta_percentual", sa.Integer(), nullable=False, server_default="80"),
        sa.Column("motivo", sa.String(), nullable=True),
        sa.Column("criado_por", sa.String(), nullable=True),
        sa.Column("aprovado_por", sa.String(), nullable=True),
        sa.Column("aprovado_em", sa.DateTime(), nullable=True),
        sa.Column("valido_de", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("valido_ate", sa.DateTime(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("provedor", "versao", name="uq_enriq_orcamento_provedor_versao"),
    )
    op.create_index("ix_enriquecimento_orcamento_global_provedor", "enriquecimento_orcamento_global", ["provedor"])
    op.create_table(
        "enriquecimento_lote_compra",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provedor", sa.String(), nullable=False),
        sa.Column("referencia", sa.String(), nullable=False),
        sa.Column("quantidade_creditos", sa.Integer(), nullable=False),
        sa.Column("custo_total_brl", sa.Numeric(18, 8), nullable=False),
        sa.Column("custo_unitario_brl", sa.Numeric(18, 8), nullable=False),
        sa.Column("comprado_em", sa.DateTime(), nullable=False),
        sa.Column("observacao", sa.String(), nullable=True),
        sa.Column("criado_por", sa.String(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("provedor", "referencia", name="uq_enriq_lote_compra_referencia"),
    )
    op.create_index("ix_enriquecimento_lote_compra_provedor", "enriquecimento_lote_compra", ["provedor"])
    op.create_table(
        "enriquecimento_politica_provedor",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provedor", sa.String(), nullable=False),
        sa.Column("versao", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("creditos_busca_por_resultado", sa.Integer(), nullable=True),
        sa.Column("creditos_email", sa.Integer(), nullable=True),
        sa.Column("creditos_telefone", sa.Integer(), nullable=True),
        sa.Column("revelar_emails", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("revelar_telefones", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("tamanho_pagina_busca", sa.Integer(), nullable=True),
        sa.Column("creditos_cliente_por_credito_provedor", sa.Integer(), nullable=True),
        sa.Column("markup_percentual", sa.Numeric(12, 4), nullable=True),
        sa.Column("metodo_custo", sa.String(), nullable=True),
        sa.Column("lote_compra_id", sa.Integer(), sa.ForeignKey("enriquecimento_lote_compra.id"), nullable=True),
        sa.Column("custo_unitario_brl", sa.Numeric(18, 8), nullable=True),
        sa.Column("preco_unitario_brl", sa.Numeric(18, 8), nullable=True),
        sa.Column("casas_exibicao", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("fonte_tarifas", sa.String(), nullable=True),
        sa.Column("motivo", sa.String(), nullable=True),
        sa.Column("criado_por", sa.String(), nullable=True),
        sa.Column("aprovado_por", sa.String(), nullable=True),
        sa.Column("aprovado_em", sa.DateTime(), nullable=True),
        sa.Column("valido_de", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("valido_ate", sa.DateTime(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("provedor", "versao", name="uq_enriq_politica_provedor_versao"),
    )
    op.create_index("ix_enriquecimento_politica_provedor_provedor", "enriquecimento_politica_provedor", ["provedor"])
    op.create_index("ix_enriquecimento_politica_provedor_lote_compra_id", "enriquecimento_politica_provedor", ["lote_compra_id"])
    op.create_table(
        "enriquecimento_uso_provedor",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provedor", sa.String(), nullable=False),
        sa.Column("lido_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("lido_por", sa.String(), nullable=True),
        sa.Column("creditos_total", sa.Integer(), nullable=True),
        sa.Column("creditos_usados", sa.Integer(), nullable=True),
        sa.Column("creditos_restantes", sa.Integer(), nullable=True),
        sa.Column("anterior_id", sa.Integer(), nullable=True),
        sa.Column("delta_provedor", sa.Integer(), nullable=True),
        sa.Column("delta_razao", sa.Integer(), nullable=True),
        sa.Column("divergencia", sa.Integer(), nullable=True),
    )
    op.create_index("ix_enriquecimento_uso_provedor_provedor", "enriquecimento_uso_provedor", ["provedor"])
    op.create_index("ix_enriquecimento_uso_provedor_lido_em", "enriquecimento_uso_provedor", ["lido_em"])
    op.create_table(
        "pesquisa_decisores",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("provedor", sa.String(), nullable=False),
        sa.Column("estado", sa.String(), nullable=False),
        sa.Column("decisores_por_empresa", sa.Integer(), nullable=False),
        sa.Column("origem_decisores", sa.String(), nullable=False),
        sa.Column("config_origem", sa.String(), nullable=False),
        sa.Column("config_id", sa.Integer(), nullable=False),
        sa.Column("config_versao", sa.Integer(), nullable=False),
        sa.Column("total_empresas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_maximo", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("estimativa", sa.JSON(), nullable=False),
        sa.Column("selecao_hash", sa.String(), nullable=False),
        sa.Column("previa_expira_em", sa.DateTime(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("confirmada_por", sa.Integer(), nullable=True),
        sa.Column("confirmada_em", sa.DateTime(), nullable=True),
        sa.Column("creditos_reservados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("creditos_consumidos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provedor_reservados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provedor_consumidos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("politica_id", sa.Integer(), nullable=True),
        sa.Column("requer_reconciliacao", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("motivo", sa.String(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_pesquisa_decisores_idempotencia"),
    )
    op.create_index("ix_pesquisa_decisores_tenant_id", "pesquisa_decisores", ["tenant_id"])
    op.create_index("ix_pesquisa_decisores_estado", "pesquisa_decisores", ["estado"])
    op.create_index("ix_pesquisa_decisores_criado_em", "pesquisa_decisores", ["criado_em"])
    op.create_table(
        "pesquisa_decisores_empresa",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pesquisa_id", sa.String(), sa.ForeignKey("pesquisa_decisores.id"), nullable=False),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("conta_id", sa.Integer(), sa.ForeignKey("conta.id"), nullable=False),
        sa.Column("estado", sa.String(), nullable=False, server_default="pendente"),
        sa.Column("decisores_existentes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("decisores_solicitados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("decisores_retornados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("creditos_reservados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("creditos_consumidos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provedor_reservados", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provedor_medidos", sa.Integer(), nullable=True),
        sa.Column("tentativas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("ids_provedor", sa.JSON(), nullable=True),
        sa.Column("motivo", sa.String(), nullable=True),
        sa.Column("enviado_em", sa.DateTime(), nullable=True),
        sa.Column("atualizado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("pesquisa_id", "conta_id", name="uq_pesquisa_decisores_empresa_conta"),
    )
    op.create_index("ix_pesquisa_decisores_empresa_pesquisa_id", "pesquisa_decisores_empresa", ["pesquisa_id"])
    op.create_index("ix_pesquisa_decisores_empresa_tenant_id", "pesquisa_decisores_empresa", ["tenant_id"])
    op.create_index("ix_pesquisa_decisores_empresa_conta_id", "pesquisa_decisores_empresa", ["conta_id"])
    op.create_table(
        "pesquisa_decisores_transicao",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("pesquisa_id", sa.String(), sa.ForeignKey("pesquisa_decisores.id"), nullable=False),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("item_id", sa.Integer(), nullable=True),
        sa.Column("estado_anterior", sa.String(), nullable=True),
        sa.Column("estado_novo", sa.String(), nullable=False),
        sa.Column("motivo", sa.Text(), nullable=True),
        sa.Column("ator_id", sa.String(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_pesquisa_decisores_transicao_pesquisa_id", "pesquisa_decisores_transicao", ["pesquisa_id"])
    op.create_index("ix_pesquisa_decisores_transicao_tenant_id", "pesquisa_decisores_transicao", ["tenant_id"])
    op.create_table(
        "enriquecimento_movimento",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("tipo", sa.String(), nullable=False),
        sa.Column("delta_saldo", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("delta_reservado", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("disponivel_apos", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provedor_delta_reservado", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("provedor_delta_consumido", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("custo_unitario_brl", sa.Numeric(18, 8), nullable=True),
        sa.Column("preco_unitario_brl", sa.Numeric(18, 8), nullable=True),
        sa.Column("custo_total_brl", sa.Numeric(18, 8), nullable=True),
        sa.Column("valor_venda_brl", sa.Numeric(18, 8), nullable=True),
        sa.Column("politica_id", sa.Integer(), nullable=True),
        sa.Column("fonte", sa.String(), nullable=True),
        sa.Column("provedor", sa.String(), nullable=True),
        sa.Column("periodo", sa.String(), nullable=True),
        sa.Column("pesquisa_id", sa.String(), sa.ForeignKey("pesquisa_decisores.id"), nullable=True),
        sa.Column("item_id", sa.Integer(), nullable=True),
        sa.Column("origem", sa.String(), nullable=True),
        sa.Column("motivo", sa.String(), nullable=True),
        sa.Column("ator_id", sa.String(), nullable=True),
        sa.Column("expira_em", sa.DateTime(), nullable=True),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_enriq_movimento_idempotencia"),
    )
    op.create_index("ix_enriquecimento_movimento_tenant_id", "enriquecimento_movimento", ["tenant_id"])
    op.create_index("ix_enriquecimento_movimento_tipo", "enriquecimento_movimento", ["tipo"])
    op.create_index("ix_enriquecimento_movimento_provedor", "enriquecimento_movimento", ["provedor"])
    op.create_index("ix_enriquecimento_movimento_fonte", "enriquecimento_movimento", ["fonte"])
    op.create_index("ix_enriquecimento_movimento_pesquisa_id", "enriquecimento_movimento", ["pesquisa_id"])
    op.create_index("ix_enriquecimento_movimento_criado_em", "enriquecimento_movimento", ["criado_em"])

    # Aporte informado pelo PO: R$ 269,94 por 400 créditos Lusha (custo unitário de referência R$ 0,67485). Só histórico de custo.
    lotes = sa.table(
        "enriquecimento_lote_compra",
        sa.column("provedor", sa.String), sa.column("referencia", sa.String), sa.column("quantidade_creditos", sa.Integer),
        sa.column("custo_total_brl", sa.Numeric), sa.column("custo_unitario_brl", sa.Numeric), sa.column("comprado_em", sa.DateTime),
        sa.column("observacao", sa.String), sa.column("criado_por", sa.String),
    )
    op.bulk_insert(lotes, [{
        "provedor": "lusha", "referencia": "APORTE-LUSHA-2026-10-21", "quantidade_creditos": 400, "custo_total_brl": Decimal("269.94"),
        "custo_unitario_brl": Decimal("0.67485"), "comprado_em": datetime(2026, 10, 21),
        "observacao": "Aporte informado pelo PO; a data é a do registro (a data exata da compra não foi informada).", "criado_por": "migracao",
    }])


def downgrade() -> None:
    for tabela in ("enriquecimento_movimento", "pesquisa_decisores_transicao", "pesquisa_decisores_empresa", "pesquisa_decisores",
                   "enriquecimento_uso_provedor", "enriquecimento_politica_provedor", "enriquecimento_lote_compra",
                   "enriquecimento_orcamento_global", "enriquecimento_config_plano", "enriquecimento_carteira"):
        op.drop_table(tabela)
