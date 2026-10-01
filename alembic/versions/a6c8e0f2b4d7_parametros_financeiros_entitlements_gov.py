"""D-075: OI-024 (entitlements Government), OI-026 (Tax Engine e parâmetros tributários iniciais) e OI-018 (câmbio).

- Planos Government: entitlements do PO por tier. Usuários em `max_usuarios`, módulos em `modulos_contratados`, API em
  `permite_api_parceiros` (onde a plataforma já os aplica) e o restante no JSON `entitlements`.
- `perfil_tributario`: `codigo_servico`; `aliquota_efetiva` deixa de ser obrigatória (o imposto é calculado por tributo).
  Perfis iniciais do PO (Lucro Presumido, São Paulo/SP, 2026) por tipo de receita. Valores não informados ficam vazios
  (o Tax Engine os aponta como pendentes): presunção de IRPJ/CSLL de licença e SaaS e ISS de SaaS e de serviços.
- `cotacao_cambio` (sem nenhuma cotação: o Financeiro informa com fonte e vigência).
- Commission Policy da margem v1: custo de IA fora da Margem Comissionável Líquida.

Revision ID: a6c8e0f2b4d7
Revises: f4a6b8c0d2e3
Create Date: 2026-10-01
"""

from datetime import date

import sqlalchemy as sa

from alembic import op

revision = "a6c8e0f2b4d7"
down_revision = "f4a6b8c0d2e3"
branch_labels = None
depends_on = None

# OI-024 — valores do PO (2026-10-01). (nome, usuários internos, API, entitlements do JSON)
ENTITLEMENTS = {
    "B2B ON Government Department": (20, False, {
        "administrative_units": 1, "storage_gb": 100, "operational_retention_months": 12, "public_procurement": "BASIC",
        "business_network": True, "corporate_brain": True, "sso": False, "support_sla": "BUSINESS_HOURS_8X5", "onboarding": "STANDARD"}),
    "B2B ON Government Professional": (50, True, {
        "administrative_units": 5, "storage_gb": 500, "operational_retention_months": 24, "public_procurement": "FULL",
        "business_network": True, "corporate_brain": True, "sso": "OPTIONAL", "support_sla": "PRIORITY_BUSINESS_HOURS_8X5",
        "onboarding": "ADVANCED"}),
    "B2B ON Government Enterprise": (100, True, {
        "administrative_units": 20, "storage_gb": 2048, "operational_retention_months": 60, "public_procurement": "FULL",
        "business_network": True, "corporate_brain": True, "sso": True, "support_sla": "CRITICAL_BUSINESS_HOURS_8X5",
        "onboarding": "DEDICATED"}),
}
MODULOS = ["map", "predator", "crm", "bids", "procurement"]  # crm, map, predator, bid_intelligence e public_procurement = true
ENTITLEMENTS_D072 = dict.fromkeys((
    "usuarios", "unidades_administrativas", "volume_operacional", "integracoes", "api", "nivel_suporte", "sla",
    "armazenamento_gb", "volume_documental", "bid_intelligence", "business_network", "corporate_brain", "agentes_ia",
))

# OI-026 — parâmetros tributários iniciais do PO. Nenhum valor além dos informados.
FONTE = "PO/CyberFort 2026-10-01 (OI-026, D-075)"
VIGENCIA = (date(2026, 1, 1), date(2027, 1, 1))  # CBS/IBS-teste valem para 2026; 2027 exige perfil novo
MUNICIPIO = "São Paulo/SP"


def _cbs_ibs(tributo: str, aliquota_teste: float) -> dict:
    return {"tributo": tributo, "base": "TESTE_REFORMA", "aliquota_teste": aliquota_teste, "aliquota_caixa_efetiva": None,
            "compensado": False, "dispensado": False, "status_conformidade": "A_CONFIRMAR"}


def _componentes(presuncao: float | None, iss: float | None) -> list[dict]:
    return [
        {"tributo": "PIS", "base": "RECEITA", "aliquota": 0.0065},
        {"tributo": "COFINS", "base": "RECEITA", "aliquota": 0.03},
        {"tributo": "IRPJ", "base": "PRESUNCAO", "aliquota": 0.15, "presuncao": presuncao},
        {"tributo": "CSLL", "base": "PRESUNCAO", "aliquota": 0.09, "presuncao": presuncao},
        {"tributo": "ISS", "base": "RECEITA", "aliquota": iss},
        _cbs_ibs("CBS", 0.009),
        _cbs_ibs("IBS", 0.001),
    ]


# (tipo de receita, código de serviço, presunção IRPJ/CSLL, ISS, observação)
PERFIS = (
    ("LICENCA_SOFTWARE", "1.05", None, 0.029,
     "1.05 — Licenciamento ou cessão de direito de uso de programas de computação (ISS 2,90% em São Paulo/SP). "
     "Percentual de presunção de IRPJ/CSLL desta receita: a informar."),
    ("SAAS", None, None, None, "Código de serviço/ISS e percentual de presunção de IRPJ/CSLL da subscrição: a informar."),
    ("SERVICO", None, 0.32, None, "Serviços sujeitos à presunção de 32%. Código de serviço/ISS da implantação: a informar."),
)
POLITICA_MARGEM = {"deduzir_custo_ia": False}


def upgrade() -> None:
    conn = op.get_bind()
    plano = sa.table("plano", sa.column("nome", sa.String), sa.column("max_usuarios", sa.Integer), sa.column("modulos_contratados", sa.JSON),
                     sa.column("permite_api_parceiros", sa.Boolean), sa.column("entitlements", sa.JSON))
    for nome, (usuarios, api, extras) in ENTITLEMENTS.items():
        conn.execute(plano.update().where(plano.c.nome == nome).values(
            max_usuarios=usuarios, modulos_contratados=MODULOS, permite_api_parceiros=api, entitlements=extras))

    with op.batch_alter_table("perfil_tributario") as tabela:
        tabela.add_column(sa.Column("codigo_servico", sa.String(), nullable=True))
        tabela.alter_column("aliquota_efetiva", existing_type=sa.Float(), nullable=True)
    perfil = sa.table(
        "perfil_tributario", sa.column("regime", sa.String), sa.column("vigente_de", sa.Date), sa.column("vigente_ate", sa.Date),
        sa.column("tipo_receita", sa.String), sa.column("municipio", sa.String), sa.column("codigo_servico", sa.String),
        sa.column("componentes", sa.JSON), sa.column("aliquota_efetiva", sa.Float), sa.column("metodo_calculo", sa.String),
        sa.column("fonte", sa.String), sa.column("observacoes", sa.String), sa.column("criado_por", sa.String),
    )
    op.bulk_insert(perfil, [
        {"regime": "LUCRO_PRESUMIDO", "vigente_de": VIGENCIA[0], "vigente_ate": VIGENCIA[1], "tipo_receita": tipo, "municipio": MUNICIPIO,
         "codigo_servico": codigo, "componentes": _componentes(presuncao, iss), "aliquota_efetiva": None, "metodo_calculo": "POR_TRIBUTO",
         "fonte": FONTE, "observacoes": observacao, "criado_por": "migracao"}
        for tipo, codigo, presuncao, iss, observacao in PERFIS
    ])

    op.create_table(
        "cotacao_cambio", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("moeda_base", sa.String(3), nullable=False),
        sa.Column("moeda_cotacao", sa.String(3), nullable=False), sa.Column("taxa", sa.Numeric(14, 6), nullable=False),
        sa.Column("fonte", sa.String(), nullable=False), sa.Column("vigente_em", sa.DateTime(), nullable=False),
        sa.Column("criado_por", sa.String(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_cotacao_cambio_par_vigencia", "cotacao_cambio", ["moeda_base", "moeda_cotacao", "vigente_em"])

    politica = sa.table("politica_comissao", sa.column("codigo", sa.String), sa.column("versao", sa.Integer), sa.column("regras", sa.JSON),
                        sa.column("ativa", sa.Boolean), sa.column("motivo", sa.String), sa.column("criado_por", sa.String))
    op.bulk_insert(politica, [{"codigo": "NET_COMMISSIONABLE_MARGIN", "versao": 1, "regras": POLITICA_MARGEM, "ativa": True,
                               "motivo": "D-075: custo de IA só entra na margem se a política disser", "criado_por": "migracao"}])


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM politica_comissao WHERE codigo = 'NET_COMMISSIONABLE_MARGIN'"))
    op.drop_index("ix_cotacao_cambio_par_vigencia", table_name="cotacao_cambio")
    op.drop_table("cotacao_cambio")
    semeados = "SELECT id FROM perfil_tributario WHERE criado_por = 'migracao' AND fonte = :fonte"
    conn.execute(sa.text(f"UPDATE apuracao_comissao SET perfil_tributario_id = NULL WHERE perfil_tributario_id IN ({semeados})"),
                 {"fonte": FONTE})
    conn.execute(sa.text("DELETE FROM perfil_tributario WHERE criado_por = 'migracao' AND fonte = :fonte"), {"fonte": FONTE})
    conn.execute(sa.text("UPDATE perfil_tributario SET aliquota_efetiva = 0 WHERE aliquota_efetiva IS NULL"))
    with op.batch_alter_table("perfil_tributario") as tabela:
        tabela.alter_column("aliquota_efetiva", existing_type=sa.Float(), nullable=False)
        tabela.drop_column("codigo_servico")
    plano = sa.table("plano", sa.column("nome", sa.String), sa.column("max_usuarios", sa.Integer), sa.column("modulos_contratados", sa.JSON),
                     sa.column("permite_api_parceiros", sa.Boolean), sa.column("entitlements", sa.JSON))
    for nome in ENTITLEMENTS:
        conn.execute(plano.update().where(plano.c.nome == nome).values(
            max_usuarios=None, modulos_contratados=["procurement"], permite_api_parceiros=False, entitlements=dict(ENTITLEMENTS_D072)))
