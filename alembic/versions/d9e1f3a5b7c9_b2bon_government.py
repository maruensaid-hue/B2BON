"""B2B ON Government (D-072): licenciamento governamental + subscrição anual.

- `plano` ganha segmento, modelo de cobrança, licença, implantação, subscrição anual, AI Credits anuais,
  "recomendado" e entitlements configuráveis. Planos privados ficam PRIVATE / MONTHLY_SUBSCRIPTION e
  com os campos novos vazios: nada muda neles.
- Três planos Government com os valores do PO (licença + implantação + subscrição anual; AI Credits/ano),
  criados só se ainda não existirem. Módulo inicial: Compras públicas (`procurement`). Limites por tier
  (usuários, unidades, SLA...) ficam "conforme contrato" (None) até o PO definir.
- Tabelas do contrato governamental (períodos, componentes, recebimentos), política de comissão versionada,
  pipeline Government e template comercial. `comissao_representante` passa a aceitar comissão de
  recebimento governamental (sem `pagamento_licenca`).

Revision ID: d9e1f3a5b7c9
Revises: c5e7a9b1d3f4
Create Date: 2026-10-01
"""

import sqlalchemy as sa

from alembic import op

revision = "d9e1f3a5b7c9"
down_revision = "c5e7a9b1d3f4"
branch_labels = None
depends_on = None

MODELO = "GOVERNMENT_LICENSE_PLUS_ANNUAL_SUBSCRIPTION"
ENTITLEMENTS = dict.fromkeys((
    "usuarios", "unidades_administrativas", "volume_operacional", "integracoes", "api", "nivel_suporte", "sla",
    "armazenamento_gb", "volume_documental", "bid_intelligence", "business_network", "corporate_brain", "agentes_ia",
))
# (nome, licença, implantação, subscrição anual, AI Credits/ano, recomendado) — valores do PO
PLANOS = (
    ("B2B ON Government Department", 72_000, 12_000, 24_000, 300_000, False),
    ("B2B ON Government Professional", 120_000, 20_000, 36_000, 600_000, True),
    ("B2B ON Government Enterprise", 180_000, 30_000, 54_000, 1_200_000, False),
)
POLITICA_V1 = {
    "gatilho": "PAYMENT_RECEIVED",
    "componentes": {
        "LICENSE": {"comissionavel": True, "taxa": 0.20},
        "INITIAL_ANNUAL_SUBSCRIPTION": {"comissionavel": True, "taxa": 0.20},
        "RENEWAL_ANNUAL_SUBSCRIPTION": {"comissionavel": True, "taxa": 0.10},
        "IMPLEMENTATION": {"comissionavel": False, "taxa": 0.20},
        "ADDITIONAL_SERVICES": {"comissionavel": False, "taxa": None},
        "ADDITIONAL_AI_CREDITS": {"comissionavel": False, "taxa": None},
    },
}
TEMPLATE_V1 = (
    "Proposta comercial — {plano}\n"
    "Órgão: {entidade}\n"
    "Referência: {referencia}\n\n"
    "LICENÇA INSTITUCIONAL: {licenca}\n"
    "IMPLANTAÇÃO: {implantacao}\n"
    "SUBSCRIÇÃO ANUAL: {assinatura}\n"
    "CONTRATAÇÃO INICIAL: {contratacao_inicial}\n"
    "AI CREDITS INCLUÍDOS: {creditos} créditos/ano\n\n"
    "RENOVAÇÃO: {assinatura}/ano, sujeito às condições contratuais aplicáveis.\n\n"
    "Condições podem ser adaptadas ao edital, ETP, Termo de Referência, modalidade de contratação e necessidades do órgão.\n"
    "Este resumo não substitui o instrumento contratual."
)
DINHEIRO = sa.Numeric(14, 2)


def _id() -> sa.Column:
    return sa.Column("id", sa.Integer(), primary_key=True)


def _criado_em() -> sa.Column:
    return sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    for coluna in (
        sa.Column("segmento", sa.String(), nullable=False, server_default="PRIVATE"),
        sa.Column("modelo_cobranca", sa.String(), nullable=False, server_default="MONTHLY_SUBSCRIPTION"),
        sa.Column("preco_licenca", DINHEIRO, nullable=True),
        sa.Column("preco_implantacao", DINHEIRO, nullable=True),
        sa.Column("preco_assinatura_anual", DINHEIRO, nullable=True),
        sa.Column("creditos_ia_anuais", sa.Integer(), nullable=True),
        sa.Column("recomendado", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("entitlements", sa.JSON(), nullable=True),
    ):
        op.add_column("plano", coluna)

    politica = op.create_table(
        "politica_comissao", _id(), sa.Column("codigo", sa.String(), nullable=False), sa.Column("versao", sa.Integer(), nullable=False),
        sa.Column("regras", sa.JSON(), nullable=False), sa.Column("ativa", sa.Boolean(), nullable=False),
        sa.Column("motivo", sa.String(), nullable=True), sa.Column("criado_por", sa.String(), nullable=True), _criado_em(),
        sa.UniqueConstraint("codigo", "versao"),
    )
    template = op.create_table(
        "template_documento_comercial", _id(), sa.Column("codigo", sa.String(), nullable=False),
        sa.Column("versao", sa.Integer(), nullable=False), sa.Column("corpo", sa.Text(), nullable=False),
        sa.Column("ativo", sa.Boolean(), nullable=False), sa.Column("criado_por", sa.String(), nullable=True), _criado_em(),
        sa.UniqueConstraint("codigo", "versao"),
    )
    op.create_table(
        "oportunidade_governo", _id(), sa.Column("titulo", sa.String(), nullable=False),
        sa.Column("entidade_governamental", sa.String(), nullable=False), sa.Column("estagio", sa.String(), nullable=False),
        sa.Column("referencia_processo", sa.String(), nullable=True), sa.Column("origem", sa.String(), nullable=True),
        sa.Column("data_prevista_fechamento", sa.Date(), nullable=True),
        sa.Column("valor_estimado_licenca", DINHEIRO, nullable=False), sa.Column("valor_estimado_assinatura", DINHEIRO, nullable=False),
        sa.Column("valor_estimado_servicos", DINHEIRO, nullable=False), sa.Column("probabilidade", sa.Float(), nullable=False),
        sa.Column("plano_id", sa.Integer(), sa.ForeignKey("plano.id"), nullable=True, index=True),
        sa.Column("representante_id", sa.Integer(), sa.ForeignKey("representante.id"), nullable=True, index=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=True, index=True), _criado_em(),
    )
    op.create_table(
        "contrato_governo", _id(), sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False, index=True),
        sa.Column("plano_id", sa.Integer(), sa.ForeignKey("plano.id"), nullable=False, index=True),
        sa.Column("oportunidade_id", sa.Integer(), sa.ForeignKey("oportunidade_governo.id"), nullable=True, index=True),
        sa.Column("modelo_cobranca", sa.String(), nullable=False), sa.Column("referencia_contrato", sa.String(), nullable=False),
        sa.Column("entidade_governamental", sa.String(), nullable=False), sa.Column("status", sa.String(), nullable=False),
        sa.Column("assinado_em", sa.Date(), nullable=False), sa.Column("valor_licenca", DINHEIRO, nullable=False),
        sa.Column("valor_implantacao", DINHEIRO, nullable=False), sa.Column("valor_assinatura_anual", DINHEIRO, nullable=False),
        sa.Column("creditos_ia_anuais", sa.Integer(), nullable=False), sa.Column("regra_reajuste", sa.JSON(), nullable=True),
        sa.Column("politica_comissao", sa.JSON(), nullable=False), sa.Column("politica_comissao_versao", sa.Integer(), nullable=True),
        sa.Column("representante_id", sa.Integer(), sa.ForeignKey("representante.id"), nullable=True, index=True),
        sa.Column("divisao_comissao", sa.JSON(), nullable=True), sa.Column("criado_por", sa.String(), nullable=True), _criado_em(),
    )
    op.create_table(
        "periodo_assinatura_governo", _id(),
        sa.Column("contrato_id", sa.Integer(), sa.ForeignKey("contrato_governo.id"), nullable=False),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False, index=True),
        sa.Column("numero", sa.Integer(), nullable=False), sa.Column("inicio", sa.Date(), nullable=False),
        sa.Column("fim", sa.Date(), nullable=False), sa.Column("valor_assinatura", DINHEIRO, nullable=False),
        sa.Column("valor_reajuste", DINHEIRO, nullable=False), sa.Column("status", sa.String(), nullable=False),
        sa.Column("status_renovacao", sa.String(), nullable=False), sa.Column("notificacao_renovacao_em", sa.DateTime(), nullable=True),
        sa.Column("lote_creditos_id", sa.Integer(), sa.ForeignKey("lote_credito.id"), nullable=True, index=True), _criado_em(),
        sa.UniqueConstraint("contrato_id", "numero"),
    )
    op.create_table(
        "componente_contrato_governo", _id(),
        sa.Column("contrato_id", sa.Integer(), sa.ForeignKey("contrato_governo.id"), nullable=False, index=True),
        sa.Column("periodo_id", sa.Integer(), sa.ForeignKey("periodo_assinatura_governo.id"), nullable=True, index=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False, index=True),
        sa.Column("tipo", sa.String(), nullable=False), sa.Column("descricao", sa.String(), nullable=True),
        sa.Column("valor", DINHEIRO, nullable=False), sa.Column("recorrente", sa.Boolean(), nullable=False),
        sa.Column("comissionavel", sa.Boolean(), nullable=False), sa.Column("taxa_comissao", sa.Float(), nullable=True),
        sa.Column("booking_em", sa.Date(), nullable=False), sa.Column("cancelado", sa.Boolean(), nullable=False), _criado_em(),
    )
    op.create_table(
        "recebimento_governo", _id(),
        sa.Column("contrato_id", sa.Integer(), sa.ForeignKey("contrato_governo.id"), nullable=False, index=True),
        sa.Column("componente_id", sa.Integer(), sa.ForeignKey("componente_contrato_governo.id"), nullable=False, index=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False, index=True),
        sa.Column("valor", DINHEIRO, nullable=False), sa.Column("recebido_em", sa.Date(), nullable=False),
        sa.Column("referencia", sa.String(), nullable=True), sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("estornado_em", sa.DateTime(), nullable=True), sa.Column("motivo_estorno", sa.String(), nullable=True),
        sa.Column("criado_por", sa.String(), nullable=True), _criado_em(), sa.UniqueConstraint("contrato_id", "idempotency_key"),
    )
    with op.batch_alter_table("comissao_representante") as tabela:
        tabela.alter_column("pagamento_licenca_id", existing_type=sa.Integer(), nullable=True)
        tabela.add_column(sa.Column("recebimento_governo_id", sa.Integer(), nullable=True))
        tabela.add_column(sa.Column("componente_governo_id", sa.Integer(), nullable=True))
        tabela.add_column(sa.Column("contrato_governo_id", sa.Integer(), nullable=True))
        for nome, tipo in (("componente_tipo", sa.String()), ("base_calculo", sa.Float()), ("taxa", sa.Float()),
                           ("fracao_divisao", sa.Float()), ("numero_renovacao", sa.Integer()), ("evento", sa.String())):
            tabela.add_column(sa.Column(nome, tipo, nullable=True))
        tabela.create_foreign_key("fk_comissao_recebimento_governo", "recebimento_governo", ["recebimento_governo_id"], ["id"])
        tabela.create_foreign_key("fk_comissao_componente_governo", "componente_contrato_governo", ["componente_governo_id"], ["id"])
        tabela.create_foreign_key("fk_comissao_contrato_governo", "contrato_governo", ["contrato_governo_id"], ["id"])
        tabela.create_unique_constraint("uq_comissao_recebimento_governo", ["recebimento_governo_id", "representante_id", "evento"])
        tabela.create_index("ix_comissao_representante_componente_governo_id", ["componente_governo_id"])
        tabela.create_index("ix_comissao_representante_contrato_governo_id", ["contrato_governo_id"])

    conn = op.get_bind()
    plano = sa.table(
        "plano", sa.column("nome", sa.String), sa.column("franquia_contas_mes", sa.Integer), sa.column("max_usuarios", sa.Integer),
        sa.column("preco_mensal", sa.Float), sa.column("visivel_self_service", sa.Boolean), sa.column("modulos_contratados", sa.JSON),
        sa.column("categoria", sa.String), sa.column("tipo_preco", sa.String), sa.column("segmento", sa.String),
        sa.column("modelo_cobranca", sa.String), sa.column("preco_licenca", DINHEIRO), sa.column("preco_implantacao", DINHEIRO),
        sa.column("preco_assinatura_anual", DINHEIRO), sa.column("creditos_ia_anuais", sa.Integer), sa.column("recomendado", sa.Boolean),
        sa.column("entitlements", sa.JSON),
    )
    novos = [
        {"nome": nome, "franquia_contas_mes": 0, "max_usuarios": None, "preco_mensal": 0.0, "visivel_self_service": False,
         "modulos_contratados": ["procurement"], "categoria": "governo", "tipo_preco": "CONTRACT", "segmento": "GOVERNMENT",
         "modelo_cobranca": MODELO, "preco_licenca": licenca, "preco_implantacao": implantacao, "preco_assinatura_anual": assinatura,
         "creditos_ia_anuais": creditos, "recomendado": recomendado, "entitlements": dict(ENTITLEMENTS)}
        for nome, licenca, implantacao, assinatura, creditos, recomendado in PLANOS
        if conn.execute(sa.text("SELECT 1 FROM plano WHERE nome = :nome"), {"nome": nome}).first() is None
    ]
    if novos:
        op.bulk_insert(plano, novos)
    op.bulk_insert(politica, [{"codigo": "GOVERNMENT", "versao": 1, "regras": POLITICA_V1, "ativa": True,
                               "motivo": "Política comercial inicial do PO (D-072)", "criado_por": "migracao"}])
    op.bulk_insert(template, [{"codigo": "PROPOSTA_GOVERNO", "versao": 1, "corpo": TEMPLATE_V1, "ativo": True, "criado_por": "migracao"}])


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM comissao_representante WHERE pagamento_licenca_id IS NULL"))
    with op.batch_alter_table("comissao_representante") as tabela:
        tabela.drop_index("ix_comissao_representante_contrato_governo_id")
        tabela.drop_index("ix_comissao_representante_componente_governo_id")
        tabela.drop_constraint("uq_comissao_recebimento_governo", type_="unique")
        tabela.drop_constraint("fk_comissao_contrato_governo", type_="foreignkey")
        tabela.drop_constraint("fk_comissao_componente_governo", type_="foreignkey")
        tabela.drop_constraint("fk_comissao_recebimento_governo", type_="foreignkey")
        for nome in ("evento", "numero_renovacao", "fracao_divisao", "taxa", "base_calculo", "componente_tipo",
                     "contrato_governo_id", "componente_governo_id", "recebimento_governo_id"):
            tabela.drop_column(nome)
        tabela.alter_column("pagamento_licenca_id", existing_type=sa.Integer(), nullable=False)
    for tabela in ("recebimento_governo", "componente_contrato_governo", "periodo_assinatura_governo", "contrato_governo",
                   "oportunidade_governo", "template_documento_comercial", "politica_comissao"):
        op.drop_table(tabela)
    for nome, *_ in PLANOS:
        em_uso = conn.execute(sa.text("SELECT 1 FROM licenca l JOIN plano p ON p.id = l.plano_id WHERE p.nome = :nome"),
                              {"nome": nome}).first()
        if em_uso is None:
            conn.execute(sa.text("DELETE FROM plano WHERE nome = :nome"), {"nome": nome})
    for coluna in ("entitlements", "recomendado", "creditos_ia_anuais", "preco_assinatura_anual", "preco_implantacao",
                   "preco_licenca", "modelo_cobranca", "segmento"):
        op.drop_column("plano", coluna)
