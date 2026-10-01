"""D-077: preços públicos verificados dos fornecedores (OI-026), Capacity Envelope, aplicabilidade e pools de custo.

- `componente_infra`: modelo de preço (FIXED_PLAN | USAGE_BASED | CUSTOM), aplicabilidade à arquitetura (APPLICABLE |
  APPLICABLE_PENDING_CONFIRMATION | AVAILABLE_NOT_ALLOCATED), provisionado para comissão, função arquitetural (dupla
  contagem), fonte do preço (tipo, URL, verificação, próxima revisão, override) e atributos.
- `envelope_capacidade`: Capacity Envelope de fornecedor por uso (quantidades decididas pela CyberFort; benchmark do
  fornecedor guardado só como referência).
- Preços públicos verificados em 2026-10-01 (páginas oficiais): Render Scale (workspace) USD 499/mês; Render Web Service
  12 CPU/96 GB USD 1.500/mês; Render Postgres USD 11.000/mês e Key Value USD 1.100/mês (disponíveis, não alocados: o banco é o
  Neon e não há Key Value na arquitetura); Render Persistent Disk USD 0,25/GB-mês (por uso, não alocado); Render Enterprise
  e Lusha Scale CUSTOM (sem preço); Neon Scale por uso (USD 0,222/CU-hora, USD 0,35/GB-mês; exemplo oficial ≈ USD 1.404 só
  como benchmark); Lusha Premium USD 399,90/mês (3.400 créditos, 5 assentos) no pool DATA_PROVIDER.
- Pesos de infraestrutura v2: STARTER/DEPARTMENT 1, PROFESSIONAL 2, ENTERPRISE 4, BID_INTELLIGENCE 2, STRATEGIC_SOURCING 4
  (o tier ENTRY passa a STARTER).

Revision ID: c8e0a2b4d6f9
Revises: b7d9f1a3c5e8
Create Date: 2026-10-01
"""

from datetime import date

import sqlalchemy as sa

from alembic import op

revision = "c8e0a2b4d6f9"
down_revision = "b7d9f1a3c5e8"
branch_labels = None
depends_on = None

VERIFICADO = date(2026, 10, 1)
REVISAO = date(2026, 12, 30)  # revisão trimestral dos preços públicos
INICIO = date(2026, 10, 1)
RENDER, NEON, LUSHA = "https://render.com/pricing", "https://neon.com/pricing", "https://www.lusha.com/pricing/"
PUBLICO = "OFFICIAL_PUBLIC_PRICING"
TIERS = {"Bid Intelligence": "BID_INTELLIGENCE", "Strategic Sourcing": "STRATEGIC_SOURCING",
         "Strategic Sourcing Enterprise": "STRATEGIC_SOURCING"}
POLITICA_INFRA_V2 = {
    "pesos": {"STARTER": 1.0, "DEPARTMENT": 1.0, "PROFESSIONAL": 2.0, "ENTERPRISE": 4.0, "BID_INTELLIGENCE": 2.0,
              "STRATEGIC_SOURCING": 4.0},
    "limiares": {"ATTENTION": 0.70, "REVIEW": 0.80, "CRITICAL": 0.90, "CAPACITY_REACHED": 1.0},
    "custo_comissao": "PROVISIONED",
    "pools_comissao": ["INFRASTRUCTURE", "DATA_PROVIDER"],
    "capacidade_unidades": None,
}


def _componente(fornecedor, servico, categoria, *, plano_referencia, custo=None, modelo="FIXED_PLAN", status="APPLICABLE",
                funcao=None, contabilizacao="INFRASTRUCTURE", metodo="WEIGHTED", url=RENDER, plano=None, atributos=None,
                observacoes=None, provisionado=True, unidade=None):
    return {"fornecedor": fornecedor, "servico": servico, "categoria": categoria, "plano": plano, "plano_referencia": plano_referencia,
            "ciclo_cobranca": "MONTHLY", "moeda": "USD", "custo_contratado": None, "custo_referencia": custo, "custo_real": None,
            "capacidade_contratada": None, "uso_atual": None, "unidade_uso": unidade, "politica_custo": "MAX_CONTRACTED_PLAN",
            "metodo_alocacao": metodo, "contabilizacao": contabilizacao, "vigente_de": INICIO, "vigente_ate": None,
            "observacoes": observacoes, "modelo_preco": modelo, "status_arquitetura": status, "provisionado_para_comissao": provisionado,
            "funcao_arquitetural": funcao, "coexistencia_justificada": None, "url_fonte": url, "tipo_fonte": PUBLICO,
            "verificado_em": VERIFICADO, "proxima_revisao_em": REVISAO, "override_manual": False, "motivo_override": None,
            "atributos": atributos, "criado_por": "migracao"}


COMPONENTES = (
    _componente("RENDER", "WORKSPACE", "HOSTING", plano_referencia="Scale", custo=499.00, status="APPLICABLE_PENDING_CONFIRMATION",
                funcao="WORKSPACE", observacoes="Maior plano de workspace com preço público. Enterprise: CUSTOM."),
    _componente("RENDER", "WEB_SERVICE_COMPUTE", "HOSTING", plano_referencia="12c-96g", custo=1500.00, plano="free (render.yaml)",
                status="APPLICABLE_PENDING_CONFIRMATION", funcao="WEB_COMPUTE",
                observacoes="Maior Web Service público (12 CPU, 96 GB) como envelope conservador do serviço principal (b2bon-api)."),
    _componente("RENDER", "POSTGRES", "DATABASE", plano_referencia="128 CPU / 1024 GB", custo=11000.00, status="AVAILABLE_NOT_ALLOCATED",
                funcao="PRIMARY_DATABASE", provisionado=False,
                observacoes="Não alocado: o banco principal é o Neon (incluir os dois seria dupla contagem)."),
    _componente("RENDER", "KEY_VALUE", "CACHE", plano_referencia="High CPU 40 GB / 40.000 conexões", custo=1100.00,
                status="AVAILABLE_NOT_ALLOCATED", funcao="CACHE", provisionado=False,
                observacoes="Só entra se a arquitetura usar Render Key Value/Redis."),
    _componente("RENDER", "PERSISTENT_DISK", "STORAGE", plano_referencia="Persistent Disk", modelo="USAGE_BASED",
                status="AVAILABLE_NOT_ALLOCATED", funcao="BLOCK_STORAGE", provisionado=False, unidade="GB",
                atributos={"precos_unitarios": {"GB_MONTH": 0.25}},
                observacoes="Por uso; o provisionado depende do storage capacity envelope."),
    _componente("RENDER", "WORKSPACE_ENTERPRISE", "HOSTING", plano_referencia="Enterprise", modelo="CUSTOM", status="AVAILABLE_NOT_ALLOCATED",
                provisionado=False, observacoes="Preço sob consulta: nenhum valor atribuído."),
    _componente("NEON", "POSTGRES", "DATABASE", plano_referencia="Scale", modelo="USAGE_BASED", funcao="PRIMARY_DATABASE", url=NEON,
                unidade="CU-hora / GB-mês", atributos={"precos_unitarios": {"CU_HOUR": 0.222, "GB_MONTH": 0.35}},
                observacoes="Banco principal (DEPLOY.md). Sem preço mensal fixo: provisionado = Capacity Envelope."),
    _componente("LUSHA", "SALES_INTELLIGENCE", "DATA_PROVIDER", plano_referencia="Premium", custo=399.90, plano="Premium",
                contabilizacao="DATA_PROVIDER", metodo="DIRECT", url=LUSHA, unidade="créditos",
                atributos={"creditos_incluidos": 3400, "assentos_incluidos": 5, "preco_referencia_fonte": "PREMIUM_PUBLIC"},
                observacoes="Maior plano com preço público. Consumo medido por tenant tem prioridade (DIRECT)."),
    _componente("LUSHA", "SALES_INTELLIGENCE_SCALE", "DATA_PROVIDER", plano_referencia="Scale", modelo="CUSTOM",
                contabilizacao="DATA_PROVIDER", status="AVAILABLE_NOT_ALLOCATED", provisionado=False, url=LUSHA,
                atributos={"modelo_comercial": "CUSTOM_ANNUAL_AGREEMENT"},
                observacoes="Preço sob consulta (contrato anual). Se contratado, entra o valor do contrato com nova vigência."),
)
BENCHMARK_NEON = {"max_unidades_computo": 10, "horas_computo_provisionadas": None, "armazenamento_gb_provisionado": 100,
                  "preco_unidade_computo": 0.222, "preco_armazenamento_gb": 0.35, "custo_mensal_estimado": 1404.00, "moeda": "USD",
                  "vigente_de": INICIO, "fonte": NEON, "verificado_em": VERIFICADO, "benchmark_only": True,
                  "observacoes": "Exemplo oficial do Neon Scale: carga variável de 4–10 CU e 100 GB ≈ USD 1.404/mês. Só referência."}
NOVAS_COLUNAS = (
    ("modelo_preco", sa.String(), "FIXED_PLAN"), ("status_arquitetura", sa.String(), "APPLICABLE"),
    ("provisionado_para_comissao", sa.Boolean(), "true"), ("funcao_arquitetural", sa.String(), None),
    ("coexistencia_justificada", sa.String(), None), ("url_fonte", sa.String(), None), ("tipo_fonte", sa.String(), "MANUAL_APPROVED"),
    ("verificado_em", sa.Date(), None), ("proxima_revisao_em", sa.Date(), None), ("override_manual", sa.Boolean(), "false"),
    ("motivo_override", sa.String(), None), ("atributos", sa.JSON(), None),
)


def upgrade() -> None:
    conn = op.get_bind()
    with op.batch_alter_table("componente_infra") as tabela:
        for nome, tipo, padrao in NOVAS_COLUNAS:
            tabela.add_column(sa.Column(nome, tipo, nullable=padrao is None, server_default=padrao))
    op.create_table(
        "envelope_capacidade", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("componente_id", sa.Integer(), sa.ForeignKey("componente_infra.id"), nullable=False, index=True),
        sa.Column("max_unidades_computo", sa.Numeric(12, 4), nullable=True),
        sa.Column("horas_computo_provisionadas", sa.Numeric(14, 4), nullable=True),
        sa.Column("armazenamento_gb_provisionado", sa.Numeric(14, 4), nullable=True),
        sa.Column("preco_unidade_computo", sa.Numeric(14, 6), nullable=True), sa.Column("preco_armazenamento_gb", sa.Numeric(14, 6), nullable=True),
        sa.Column("outros_custos", sa.JSON(), nullable=True), sa.Column("custo_mensal_estimado", sa.Numeric(14, 2), nullable=True),
        sa.Column("moeda", sa.String(3), nullable=False), sa.Column("vigente_de", sa.Date(), nullable=False),
        sa.Column("vigente_ate", sa.Date(), nullable=True), sa.Column("fonte", sa.String(), nullable=True),
        sa.Column("verificado_em", sa.Date(), nullable=True), sa.Column("benchmark_only", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("observacoes", sa.String(), nullable=True), sa.Column("criado_por", sa.String(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    conn.execute(sa.text("UPDATE plano SET tier_infraestrutura = 'STARTER' WHERE tier_infraestrutura = 'ENTRY'"))
    for nome, tier in TIERS.items():
        conn.execute(sa.text("UPDATE plano SET tier_infraestrutura = :tier WHERE nome = :nome"), {"tier": tier, "nome": nome})
    conn.execute(sa.text("UPDATE politica_comissao SET ativa = false WHERE codigo = 'INFRASTRUCTURE_COST_POLICY'"))
    politica = sa.table("politica_comissao", sa.column("codigo", sa.String), sa.column("versao", sa.Integer), sa.column("regras", sa.JSON),
                        sa.column("ativa", sa.Boolean), sa.column("motivo", sa.String), sa.column("criado_por", sa.String))
    versao = (conn.execute(sa.text("SELECT max(versao) FROM politica_comissao WHERE codigo = 'INFRASTRUCTURE_COST_POLICY'")).scalar() or 0) + 1
    op.bulk_insert(politica, [{"codigo": "INFRASTRUCTURE_COST_POLICY", "versao": versao, "regras": POLITICA_INFRA_V2, "ativa": True,
                               "motivo": "D-077: pesos de Bid Intelligence (2) e Strategic Sourcing (4); pools INFRASTRUCTURE e DATA_PROVIDER",
                               "criado_por": "migracao"}])
    tabela = sa.table("componente_infra", *[sa.column(c, sa.JSON) if c == "atributos" else sa.column(c) for c in COMPONENTES[0]])
    op.bulk_insert(tabela, list(COMPONENTES))
    neon_id = conn.execute(sa.text("SELECT id FROM componente_infra WHERE fornecedor = 'NEON' AND criado_por = 'migracao'")).scalar()
    envelope = sa.table("envelope_capacidade", sa.column("componente_id"), *[sa.column(c) for c in BENCHMARK_NEON])
    op.bulk_insert(envelope, [{"componente_id": neon_id, **BENCHMARK_NEON}])


def downgrade() -> None:
    conn = op.get_bind()
    op.drop_table("envelope_capacidade")
    seeds = "SELECT id FROM componente_infra WHERE criado_por = 'migracao' AND verificado_em = :v"
    for tabela in ("alerta_capacidade_infra", "custo_direto_infra", "uso_capacidade_infra"):
        conn.execute(sa.text(f"DELETE FROM {tabela} WHERE componente_id IN ({seeds})"), {"v": VERIFICADO})
    conn.execute(sa.text("DELETE FROM componente_infra WHERE criado_por = 'migracao' AND verificado_em = :v"), {"v": VERIFICADO})
    with op.batch_alter_table("componente_infra") as tabela:
        for nome, _, _ in reversed(NOVAS_COLUNAS):
            tabela.drop_column(nome)
    versao = conn.execute(sa.text("SELECT max(versao) FROM politica_comissao WHERE codigo = 'INFRASTRUCTURE_COST_POLICY'")).scalar()
    conn.execute(sa.text("DELETE FROM politica_comissao WHERE codigo = 'INFRASTRUCTURE_COST_POLICY' AND versao = :v AND criado_por = 'migracao'"),
                 {"v": versao})
    conn.execute(sa.text("UPDATE politica_comissao SET ativa = true WHERE codigo = 'INFRASTRUCTURE_COST_POLICY' AND versao = "
                         "(SELECT max(versao) FROM politica_comissao WHERE codigo = 'INFRASTRUCTURE_COST_POLICY')"))
    for nome in TIERS:
        conn.execute(sa.text("UPDATE plano SET tier_infraestrutura = NULL WHERE nome = :nome"), {"nome": nome})
    conn.execute(sa.text("UPDATE plano SET tier_infraestrutura = 'ENTERPRISE' WHERE nome = 'Strategic Sourcing Enterprise'"))
    conn.execute(sa.text("UPDATE plano SET tier_infraestrutura = 'ENTRY' WHERE tier_infraestrutura = 'STARTER'"))
