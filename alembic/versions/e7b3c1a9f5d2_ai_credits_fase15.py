"""Fase 15: B2B ON AI Credits (pacotes, catálogo de workloads versionado,
lotes, execuções, compras, configuração por tenant, alertas, cache) e
migração dos saldos legados da carteira para lotes (sem perder saldo).

Revision ID: e7b3c1a9f5d2
Revises: c4f1a9e7d2b3
Create Date: 2026-09-25
"""

import sqlalchemy as sa

from alembic import op

revision = "e7b3c1a9f5d2"
down_revision = "c4f1a9e7d2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pacote_credito",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("codigo", sa.String(), nullable=False, index=True),
        sa.Column("nome", sa.String(), nullable=False),
        sa.Column("versao", sa.Integer(), nullable=False),
        sa.Column("moeda", sa.String(), nullable=False),
        sa.Column("creditos", sa.Integer(), nullable=True),
        sa.Column("preco", sa.Numeric(14, 2), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("validade_meses", sa.Integer(), nullable=True),
        sa.Column("ordem", sa.Integer(), nullable=False),
        sa.Column("valido_de", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("valido_ate", sa.DateTime(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("codigo", "versao"),
    )
    op.create_table(
        "catalogo_credito",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("versao", sa.String(), nullable=False, unique=True),
        sa.Column("numero", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("motivo", sa.String(), nullable=True),
        sa.Column("criado_por", sa.String(), nullable=True),
        sa.Column("aprovado_por", sa.String(), nullable=True),
        sa.Column("vigente_desde", sa.DateTime(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "workload_ia",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("catalogo_id", sa.Integer(), sa.ForeignKey("catalogo_credito.id"), nullable=False, index=True),
        sa.Column("codigo", sa.String(), nullable=False),
        sa.Column("modulo", sa.String(), nullable=False),
        sa.Column("nome", sa.String(), nullable=False),
        sa.Column("descricao", sa.String(), nullable=True),
        sa.Column("classe", sa.String(), nullable=False),
        sa.Column("creditos_base", sa.Numeric(12, 2), nullable=False),
        sa.Column("creditos_min", sa.Numeric(12, 2), nullable=True),
        sa.Column("creditos_max", sa.Numeric(12, 2), nullable=True),
        sa.Column("politica_variavel", sa.JSON(), nullable=True),
        sa.Column("politica_modelo", sa.JSON(), nullable=True),
        sa.Column("custo_max_usd", sa.Numeric(12, 4), nullable=True),
        sa.Column("margem_alvo", sa.Numeric(5, 4), nullable=True),
        sa.Column("requer_aprovacao", sa.Boolean(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("catalogo_id", "codigo"),
    )
    op.create_table(
        "lote_credito",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False, index=True),
        sa.Column("tipo", sa.String(), nullable=False),
        sa.Column("origem", sa.String(), nullable=False),
        sa.Column("referencia", sa.String(), nullable=True),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("concedido_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("expira_em", sa.DateTime(), nullable=True),
        sa.Column("quantidade_original", sa.Numeric(18, 4), nullable=False),
        sa.Column("quantidade_restante", sa.Numeric(18, 4), nullable=False),
        sa.Column("receita_por_credito_brl", sa.Numeric(14, 8), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.UniqueConstraint("tenant_id", "idempotency_key"),
    )
    op.create_table(
        "execucao_ia",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False, index=True),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("workload_codigo", sa.String(), nullable=False, index=True),
        sa.Column("catalogo_versao", sa.String(), nullable=False),
        sa.Column("classe", sa.String(), nullable=False),
        sa.Column("modulo", sa.String(), nullable=False, index=True),
        sa.Column("feature", sa.String(), nullable=True),
        sa.Column("agente", sa.String(), nullable=True),
        sa.Column("gatilho", sa.String(), nullable=True),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("plano_id", sa.Integer(), nullable=True),
        sa.Column("parametros", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, index=True),
        sa.Column("creditos_estimados", sa.Numeric(14, 4), nullable=False),
        sa.Column("creditos_reservados", sa.Numeric(14, 4), nullable=False),
        sa.Column("creditos_liquidados", sa.Numeric(14, 4), nullable=False),
        sa.Column("creditos_excedente", sa.Numeric(14, 4), nullable=False),
        sa.Column("chamadas", sa.Integer(), nullable=False),
        sa.Column("custo_llm_usd", sa.Numeric(14, 6), nullable=False),
        sa.Column("custo_dados_usd", sa.Numeric(14, 6), nullable=False),
        sa.Column("custo_total_usd", sa.Numeric(14, 6), nullable=False),
        sa.Column("custo_desconhecido", sa.Boolean(), nullable=False),
        sa.Column("economia_cache_usd", sa.Numeric(14, 6), nullable=False),
        sa.Column("cache_hits", sa.Integer(), nullable=False),
        sa.Column("cambio_usd_brl", sa.Numeric(10, 4), nullable=True),
        sa.Column("custo_total_brl", sa.Numeric(14, 4), nullable=True),
        sa.Column("receita_brl", sa.Numeric(14, 4), nullable=True),
        sa.Column("lucro_bruto_brl", sa.Numeric(14, 4), nullable=True),
        sa.Column("margem_bruta", sa.Numeric(8, 4), nullable=True),
        sa.Column("motivo_estorno", sa.String(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False, index=True),
        sa.Column("liquidado_em", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("tenant_id", "idempotency_key"),
    )
    op.create_table(
        "compra_credito",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False, index=True),
        sa.Column("pacote_id", sa.Integer(), sa.ForeignKey("pacote_credito.id"), nullable=False, index=True),
        sa.Column("pacote_codigo", sa.String(), nullable=False),
        sa.Column("pacote_versao", sa.Integer(), nullable=False),
        sa.Column("creditos", sa.Integer(), nullable=False),
        sa.Column("preco", sa.Numeric(14, 2), nullable=False),
        sa.Column("moeda", sa.String(), nullable=False),
        sa.Column("validade_meses", sa.Integer(), nullable=True),
        sa.Column("origem", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("preferencia_id_externo", sa.String(), nullable=True),
        sa.Column("url_checkout", sa.String(), nullable=True),
        sa.Column("pagamento_id_externo", sa.String(), nullable=True, unique=True),
        sa.Column("lote_id", sa.Integer(), sa.ForeignKey("lote_credito.id"), nullable=True, index=True),
        sa.Column("criado_por", sa.String(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("confirmado_em", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "configuracao_credito_tenant",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False, unique=True),
        sa.Column("franquia_personalizada", sa.Integer(), nullable=True),
        sa.Column("recarga_ativa", sa.Boolean(), nullable=False),
        sa.Column("recarga_limiar", sa.Integer(), nullable=True),
        sa.Column("recarga_pacote_codigo", sa.String(), nullable=True),
        sa.Column("recarga_consentido_por", sa.String(), nullable=True),
        sa.Column("recarga_consentido_em", sa.DateTime(), nullable=True),
        sa.Column("excedente_ativo", sa.Boolean(), nullable=False),
        sa.Column("excedente_orcamento_mensal", sa.Integer(), nullable=True),
        sa.Column("excedente_limite_suave", sa.Integer(), nullable=True),
        sa.Column("excedente_limite_rigido", sa.Integer(), nullable=True),
        sa.Column("excedente_aprovado_por", sa.String(), nullable=True),
        sa.Column("orcamento_mensal_creditos", sa.Integer(), nullable=True),
        sa.Column("limite_diario_creditos", sa.Integer(), nullable=True),
        sa.Column("limite_usuario_creditos", sa.Integer(), nullable=True),
        sa.Column("limite_api_creditos", sa.Integer(), nullable=True),
        sa.Column("limites_modulo_percentual", sa.JSON(), nullable=True),
        sa.Column("limites_agente_creditos", sa.JSON(), nullable=True),
        sa.Column("percentual_alerta", sa.Integer(), nullable=False),
        sa.Column("parada_rigida", sa.Boolean(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "alerta_credito",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False, index=True),
        sa.Column("periodo", sa.String(), nullable=False),
        sa.Column("nivel", sa.Integer(), nullable=False),
        sa.Column("percentual", sa.Numeric(6, 2), nullable=False),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "periodo", "nivel"),
    )
    op.create_table(
        "cache_resposta_ia",
        sa.Column("chave", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False, index=True),
        sa.Column("feature", sa.String(), nullable=False),
        sa.Column("modelo", sa.String(), nullable=True),
        sa.Column("conteudo", sa.String(), nullable=False),
        sa.Column("custo_original_usd", sa.Numeric(14, 6), nullable=True),
        sa.Column("tokens_entrada", sa.Integer(), nullable=False),
        sa.Column("tokens_saida", sa.Integer(), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("expira_em", sa.DateTime(), nullable=False),
    )

    with op.batch_alter_table("movimento_credito") as tabela:
        tabela.add_column(sa.Column("lote_id", sa.Integer(), nullable=True))
        tabela.add_column(sa.Column("execucao_id", sa.String(), nullable=True))
        tabela.create_foreign_key("fk_movimento_credito_lote_id", "lote_credito", ["lote_id"], ["id"])
        tabela.create_foreign_key("fk_movimento_credito_execucao_id", "execucao_ia", ["execucao_id"], ["id"])
        tabela.add_column(sa.Column("idempotency_key", sa.String(), nullable=True))
        tabela.add_column(sa.Column("receita_brl", sa.Numeric(14, 4), nullable=True))
        tabela.add_column(sa.Column("catalogo_versao", sa.String(), nullable=True))
        tabela.add_column(sa.Column("faturavel", sa.Boolean(), server_default=sa.false(), nullable=False))
        tabela.create_unique_constraint("uq_movimento_credito_tenant_idempotency", ["tenant_id", "idempotency_key"])
        tabela.create_index("ix_movimento_credito_lote_id", ["lote_id"])
        tabela.create_index("ix_movimento_credito_execucao_id", ["execucao_id"])

    with op.batch_alter_table("registro_uso_ia") as tabela:
        tabela.add_column(sa.Column("execucao_id", sa.String(), nullable=True))
        tabela.add_column(sa.Column("workload_codigo", sa.String(), nullable=True))
        tabela.add_column(sa.Column("catalogo_versao", sa.String(), nullable=True))
        tabela.add_column(sa.Column("cache_hit", sa.Boolean(), server_default=sa.false(), nullable=False))
        tabela.add_column(sa.Column("economia_cache_usd", sa.Numeric(14, 6), nullable=True))
        tabela.add_column(sa.Column("custo_dados_usd", sa.Numeric(14, 6), nullable=True))
        tabela.add_column(sa.Column("tokens_embedding", sa.Integer(), server_default="0", nullable=False))
        tabela.add_column(sa.Column("chamadas_ferramenta", sa.Integer(), server_default="0", nullable=False))
        tabela.add_column(sa.Column("decisao_roteamento", sa.String(), nullable=True))
        tabela.create_index("ix_registro_uso_ia_execucao_id", ["execucao_id"])
        tabela.create_index("ix_registro_uso_ia_workload_codigo", ["workload_codigo"])

    # Saldos da carteira legada (Fase 5) viram lote ADJUSTMENT, sem validade,
    # com o mesmo valor. Movimentos antigos ficam como estão (histórico).
    conexao = op.get_bind()
    carteiras = conexao.execute(sa.text("SELECT tenant_id, saldo FROM carteira_creditos WHERE saldo > 0")).fetchall()
    for tenant_id, saldo in carteiras:
        conexao.execute(
            sa.text(
                "INSERT INTO lote_credito (tenant_id, tipo, origem, referencia, idempotency_key, quantidade_original, "
                "quantidade_restante, receita_por_credito_brl, status) VALUES (:t, 'ADJUSTMENT', 'MIGRACAO_FASE_15', "
                "'carteira_creditos', :k, :s, :s, 0, 'ATIVO')"
            ),
            {"t": tenant_id, "k": f"migracao-fase15:{tenant_id}", "s": saldo},
        )
        lote_id = conexao.execute(
            sa.text("SELECT id FROM lote_credito WHERE tenant_id = :t AND idempotency_key = :k"),
            {"t": tenant_id, "k": f"migracao-fase15:{tenant_id}"},
        ).scalar()
        conexao.execute(
            sa.text(
                "INSERT INTO movimento_credito (tenant_id, tipo, quantidade, saldo_apos, descricao, lote_id, idempotency_key, "
                "faturavel) VALUES (:t, 'CREDIT_ADJUSTED', :s, :s, 'Saldo migrado da carteira da Fase 5', :l, :k, false)"
            ),
            {"t": tenant_id, "s": saldo, "l": lote_id, "k": f"migracao-fase15:{tenant_id}"},
        )


def downgrade() -> None:
    with op.batch_alter_table("registro_uso_ia") as tabela:
        tabela.drop_index("ix_registro_uso_ia_workload_codigo")
        tabela.drop_index("ix_registro_uso_ia_execucao_id")
        for coluna in ("decisao_roteamento", "chamadas_ferramenta", "tokens_embedding", "custo_dados_usd", "economia_cache_usd",
                       "cache_hit", "catalogo_versao", "workload_codigo", "execucao_id"):
            tabela.drop_column(coluna)
    with op.batch_alter_table("movimento_credito") as tabela:
        tabela.drop_index("ix_movimento_credito_execucao_id")
        tabela.drop_index("ix_movimento_credito_lote_id")
        tabela.drop_constraint("uq_movimento_credito_tenant_idempotency", type_="unique")
        tabela.drop_constraint("fk_movimento_credito_execucao_id", type_="foreignkey")
        tabela.drop_constraint("fk_movimento_credito_lote_id", type_="foreignkey")
        for coluna in ("faturavel", "catalogo_versao", "receita_brl", "idempotency_key", "execucao_id", "lote_id"):
            tabela.drop_column(coluna)
    for tabela in ("cache_resposta_ia", "alerta_credito", "configuracao_credito_tenant", "compra_credito", "execucao_ia",
                   "lote_credito", "workload_ia", "catalogo_credito", "pacote_credito"):
        op.drop_table(tabela)
