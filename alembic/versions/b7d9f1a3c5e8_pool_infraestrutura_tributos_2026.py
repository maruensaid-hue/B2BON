"""D-076: Infrastructure Cost Pool (OI-026), Tax Profiles 2026 revisados, PTAX (OI-018) e franquias Government (OI-024).

- Infrastructure Cost Pool: `componente_infra` (fornecedor/plano com custo contratado, de referência e real, capacidade,
  uso, política de custo e método de alocação), `uso_capacidade_infra`, `custo_direto_infra`, `alerta_capacidade_infra`.
  Nenhum fornecedor ou valor criado (o PO cadastra). Sai o `modelo_custo_infra` da D-075 (sem dados em produção).
- `apuracao_comissao`: custo provisionado (comissão) e real separados, meses de operação remunerados, marca d'água dos
  custos diretos; tipos de receita D-076 (SOFTWARE_LICENSE, SAAS_SUBSCRIPTION, IMPLEMENTATION...).
- Política de infraestrutura v1 (pesos ENTRY/DEPARTMENT 1, PROFESSIONAL 2, ENTERPRISE 4; limiares 70/80/90/100%; comissão
  sobre o custo PROVISIONADO). Tier de infraestrutura dos planos pelo nome (Starter = ENTRY; Professional; Enterprise;
  ofertas Government) — plano sem tier não entra na alocação.
- Tax Profiles 2026 (São Paulo/SP): os da D-075 ficam encerrados na própria vigência e entram os do PO — SOFTWARE_LICENSE
  (1.05 / 2800), SAAS_SUBSCRIPTION (serviço, ISS a informar) e IMPLEMENTATION (1.07 / 2919), com presunção de 32%,
  acréscimo de presunção de 2026, adicional de IRPJ e CBS/IBS-teste com situação a confirmar.
- `cotacao_cambio`: tipo (PTAX_CLOSE | MANUAL), data da cotação e momento da obtenção.
- Franquia mensal de contas Government: 1.000 / 3.000 / 10.000 (separada dos AI Credits).

Revision ID: b7d9f1a3c5e8
Revises: a6c8e0f2b4d7
Create Date: 2026-10-01
"""

from datetime import date

import sqlalchemy as sa

from alembic import op

revision = "b7d9f1a3c5e8"
down_revision = "a6c8e0f2b4d7"
branch_labels = None
depends_on = None

DINHEIRO = sa.Numeric(14, 2)
QUANTIDADE = sa.Numeric(18, 4)
FONTE_D075 = "PO/CyberFort 2026-10-01 (OI-026, D-075)"
FONTE = "PO/CyberFort 2026-10-01 (OI-026, D-076)"
VERSAO_LEGAL = "2026-v1"
VIGENCIA = (date(2026, 1, 1), date(2027, 1, 1))
MUNICIPIO = "São Paulo/SP"
TIERS_GOVERNO = {"B2B ON Government Department": "DEPARTMENT", "B2B ON Government Professional": "PROFESSIONAL",
                 "B2B ON Government Enterprise": "ENTERPRISE"}
FRANQUIA_GOVERNO = {"B2B ON Government Department": 1_000, "B2B ON Government Professional": 3_000,
                    "B2B ON Government Enterprise": 10_000}
POLITICA_INFRA = {
    "pesos": {"ENTRY": 1.0, "DEPARTMENT": 1.0, "PROFESSIONAL": 2.0, "ENTERPRISE": 4.0},
    "limiares": {"ATTENTION": 0.70, "REVIEW": 0.80, "CRITICAL": 0.90, "CAPACITY_REACHED": 1.0},
    "custo_comissao": "PROVISIONED",
}
TIPOS_D075 = {"LICENCA_SOFTWARE": "SOFTWARE_LICENSE", "SAAS": "SAAS_SUBSCRIPTION"}
ACRESCIMO_2026 = {"percentual": 0.10, "limite_anual": 5_000_000, "periodo": "TRIMESTRAL"}


def tier_por_nome(nome: str) -> str | None:
    if nome in TIERS_GOVERNO:
        return TIERS_GOVERNO[nome]
    for sufixo, tier in (("Starter", "ENTRY"), ("Professional", "PROFESSIONAL"), ("Enterprise", "ENTERPRISE")):
        if nome == sufixo or nome.endswith(f" {sufixo}"):
            return tier
    return None


def _cbs_ibs(tributo: str, aliquota_teste: float) -> dict:
    return {"tributo": tributo, "base": "TESTE_REFORMA", "aliquota_teste": aliquota_teste, "aliquota_caixa_efetiva": None,
            "situacao": "PENDING_COMPLIANCE_CONFIRMATION"}


def componentes(presuncao: float | None, iss: float | None) -> list[dict]:
    return [
        {"tributo": "PIS", "base": "RECEITA", "aliquota": 0.0065},
        {"tributo": "COFINS", "base": "RECEITA", "aliquota": 0.03},
        {"tributo": "IRPJ", "base": "PRESUNCAO", "aliquota": 0.15, "presuncao": presuncao, "acrescimo_presuncao": dict(ACRESCIMO_2026)},
        {"tributo": "IRPJ_ADDITIONAL", "base": "PRESUNCAO_EXCEDENTE", "aliquota": 0.10, "limite_mensal": 20_000, "periodo": "TRIMESTRAL"},
        {"tributo": "CSLL", "base": "PRESUNCAO", "aliquota": 0.09, "presuncao": presuncao, "acrescimo_presuncao": dict(ACRESCIMO_2026)},
        {"tributo": "ISS", "base": "RECEITA", "aliquota": iss},
        _cbs_ibs("CBS", 0.009),
        _cbs_ibs("IBS", 0.001),
    ]


# (tipo de receita, item LC 116, código municipal, presunção IRPJ/CSLL, ISS, observação)
PERFIS = (
    ("SOFTWARE_LICENSE", "1.05", "2800", 0.32, 0.029,
     "Licenciamento ou cessão de direito de uso de programas de computação, inclusive distribuição."),
    ("SAAS_SUBSCRIPTION", None, None, 0.32, None,
     "Subscrição SaaS na categoria de serviço para simulação financeira (classificação a validar pela contabilidade). "
     "Item/código de serviço e ISS: a informar."),
    ("IMPLEMENTATION", "1.07", "2919", 0.32, 0.029,
     "Implantação com escopo de suporte técnico, instalação, configuração e manutenção de software/banco de dados. "
     "Escopo de consultoria ou outra atividade usa o perfil correspondente."),
)


def _meses_periodo(inicio: date, fim: date) -> float:
    return max((fim.year - inicio.year) * 12 + fim.month - inicio.month + (fim.day - inicio.day) / 30, 0)


def upgrade() -> None:
    conn = op.get_bind()
    with op.batch_alter_table("plano") as tabela:
        tabela.add_column(sa.Column("tier_infraestrutura", sa.String(), nullable=True))
    for plano_id, nome in conn.execute(sa.text("SELECT id, nome FROM plano")).fetchall():
        conn.execute(sa.text("UPDATE plano SET tier_infraestrutura = :tier WHERE id = :id"), {"tier": tier_por_nome(nome), "id": plano_id})
    for nome, contas in FRANQUIA_GOVERNO.items():
        conn.execute(sa.text("UPDATE plano SET franquia_contas_mes = :contas WHERE nome = :nome"), {"contas": contas, "nome": nome})

    op.create_table(
        "componente_infra", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("fornecedor", sa.String(), nullable=False),
        sa.Column("servico", sa.String(), nullable=False), sa.Column("categoria", sa.String(), nullable=False),
        sa.Column("plano", sa.String(), nullable=True), sa.Column("plano_referencia", sa.String(), nullable=True),
        sa.Column("ciclo_cobranca", sa.String(), nullable=False), sa.Column("moeda", sa.String(3), nullable=False),
        sa.Column("custo_contratado", DINHEIRO, nullable=True), sa.Column("custo_referencia", DINHEIRO, nullable=True),
        sa.Column("custo_real", DINHEIRO, nullable=True), sa.Column("capacidade_contratada", QUANTIDADE, nullable=True),
        sa.Column("uso_atual", QUANTIDADE, nullable=True), sa.Column("unidade_uso", sa.String(), nullable=True),
        sa.Column("politica_custo", sa.String(), nullable=False), sa.Column("metodo_alocacao", sa.String(), nullable=False),
        sa.Column("contabilizacao", sa.String(), nullable=False), sa.Column("vigente_de", sa.Date(), nullable=False),
        sa.Column("vigente_ate", sa.Date(), nullable=True), sa.Column("observacoes", sa.String(), nullable=True),
        sa.Column("criado_por", sa.String(), nullable=True), sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "uso_capacidade_infra", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("componente_id", sa.Integer(), sa.ForeignKey("componente_infra.id"), nullable=False, index=True),
        sa.Column("medido_em", sa.DateTime(), nullable=False), sa.Column("uso", QUANTIDADE, nullable=False),
        sa.Column("fonte", sa.String(), nullable=True), sa.Column("registrado_por", sa.String(), nullable=True),
    )
    op.create_table(
        "custo_direto_infra", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("componente_id", sa.Integer(), sa.ForeignKey("componente_infra.id"), nullable=False, index=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False, index=True),
        sa.Column("competencia", sa.String(7), nullable=False), sa.Column("quantidade", QUANTIDADE, nullable=True),
        sa.Column("custo", DINHEIRO, nullable=False), sa.Column("fonte", sa.String(), nullable=True),
        sa.Column("criado_por", sa.String(), nullable=True), sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "alerta_capacidade_infra", sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("componente_id", sa.Integer(), sa.ForeignKey("componente_infra.id"), nullable=False, index=True),
        sa.Column("nivel", sa.String(), nullable=False), sa.Column("utilizacao", sa.Float(), nullable=False),
        sa.Column("mensagem", sa.String(), nullable=False), sa.Column("status", sa.String(), nullable=False),
        sa.Column("decisao", sa.String(), nullable=True), sa.Column("decidido_por", sa.String(), nullable=True),
        sa.Column("decidido_em", sa.DateTime(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )

    with op.batch_alter_table("apuracao_comissao") as tabela:
        tabela.add_column(sa.Column("custo_infra_real", DINHEIRO, nullable=True))
        tabela.add_column(sa.Column("meses_infra", sa.Float(), nullable=True))
        tabela.add_column(sa.Column("custo_direto_ate", sa.String(7), nullable=True))
        tabela.drop_index("ix_apuracao_comissao_modelo_custo_infra_id")
        tabela.drop_column("modelo_custo_infra_id")
    op.drop_table("modelo_custo_infra")
    for antigo, novo in TIPOS_D075.items():
        conn.execute(sa.text("UPDATE apuracao_comissao SET tipo_receita = :novo WHERE tipo_receita = :antigo"), {"novo": novo, "antigo": antigo})
    conn.execute(sa.text("UPDATE apuracao_comissao SET tipo_receita = CASE WHEN componente_tipo = 'IMPLEMENTATION' THEN 'IMPLEMENTATION' "
                         "ELSE 'UNCLASSIFIED' END WHERE tipo_receita = 'SERVICO'"))
    conn.execute(sa.text("UPDATE apuracao_comissao SET meses_infra = 1 WHERE origem = 'PAGAMENTO_LICENCA'"))
    operacionais = conn.execute(sa.text(
        "SELECT a.id, r.valor, c.valor, p.inicio, p.fim FROM apuracao_comissao a "
        "JOIN recebimento_governo r ON r.id = a.recebimento_governo_id JOIN componente_contrato_governo c ON c.id = r.componente_id "
        "JOIN periodo_assinatura_governo p ON p.id = c.periodo_id "
        "WHERE a.componente_tipo IN ('INITIAL_ANNUAL_SUBSCRIPTION', 'RENEWAL_ANNUAL_SUBSCRIPTION')")).fetchall()
    for apuracao_id, recebido, componente, inicio, fim in operacionais:
        inicio, fim = (date.fromisoformat(str(inicio)[:10]), date.fromisoformat(str(fim)[:10]))
        meses = round(_meses_periodo(inicio, fim) * float(recebido) / float(componente), 4) if componente else 0
        conn.execute(sa.text("UPDATE apuracao_comissao SET meses_infra = :m WHERE id = :id"), {"m": meses, "id": apuracao_id})
    conn.execute(sa.text("UPDATE apuracao_comissao SET meses_infra = 0 WHERE meses_infra IS NULL"))

    with op.batch_alter_table("perfil_tributario") as tabela:
        tabela.add_column(sa.Column("item_lista_servico", sa.String(), nullable=True))
        tabela.add_column(sa.Column("versao_legal", sa.String(), nullable=True))
    conn.execute(sa.text("UPDATE perfil_tributario SET vigente_ate = vigente_de, observacoes = 'Substituído pela D-076 (mesma vigência).' "
                         "WHERE fonte = :fonte"), {"fonte": FONTE_D075})
    perfil = sa.table(
        "perfil_tributario", sa.column("regime", sa.String), sa.column("vigente_de", sa.Date), sa.column("vigente_ate", sa.Date),
        sa.column("tipo_receita", sa.String), sa.column("municipio", sa.String), sa.column("item_lista_servico", sa.String),
        sa.column("codigo_servico", sa.String), sa.column("versao_legal", sa.String), sa.column("componentes", sa.JSON),
        sa.column("aliquota_efetiva", sa.Float), sa.column("metodo_calculo", sa.String), sa.column("fonte", sa.String),
        sa.column("observacoes", sa.String), sa.column("criado_por", sa.String),
    )
    op.bulk_insert(perfil, [
        {"regime": "LUCRO_PRESUMIDO", "vigente_de": VIGENCIA[0], "vigente_ate": VIGENCIA[1], "tipo_receita": tipo, "municipio": MUNICIPIO,
         "item_lista_servico": item, "codigo_servico": codigo, "versao_legal": VERSAO_LEGAL, "componentes": componentes(presuncao, iss),
         "aliquota_efetiva": None, "metodo_calculo": "POR_TRIBUTO", "fonte": FONTE, "observacoes": observacao, "criado_por": "migracao"}
        for tipo, item, codigo, presuncao, iss, observacao in PERFIS
    ])

    with op.batch_alter_table("cotacao_cambio") as tabela:
        tabela.add_column(sa.Column("tipo", sa.String(), server_default="MANUAL", nullable=False))
        tabela.add_column(sa.Column("data_cotacao", sa.Date(), nullable=True))
        tabela.add_column(sa.Column("obtida_em", sa.DateTime(), nullable=True))
    with op.batch_alter_table("componente_contrato_governo") as tabela:
        tabela.add_column(sa.Column("tipo_receita", sa.String(), nullable=True))

    politica = sa.table("politica_comissao", sa.column("codigo", sa.String), sa.column("versao", sa.Integer), sa.column("regras", sa.JSON),
                        sa.column("ativa", sa.Boolean), sa.column("motivo", sa.String), sa.column("criado_por", sa.String))
    op.bulk_insert(politica, [{"codigo": "INFRASTRUCTURE_COST_POLICY", "versao": 1, "regras": POLITICA_INFRA, "ativa": True,
                               "motivo": "D-076: plano máximo, pesos 1/1/2/4, limiares 70/80/90/100%", "criado_por": "migracao"}])


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM politica_comissao WHERE codigo = 'INFRASTRUCTURE_COST_POLICY'"))
    with op.batch_alter_table("componente_contrato_governo") as tabela:
        tabela.drop_column("tipo_receita")
    with op.batch_alter_table("cotacao_cambio") as tabela:
        tabela.drop_column("obtida_em")
        tabela.drop_column("data_cotacao")
        tabela.drop_column("tipo")
    novos = "SELECT id FROM perfil_tributario WHERE fonte = :fonte"
    conn.execute(sa.text(f"UPDATE apuracao_comissao SET perfil_tributario_id = NULL WHERE perfil_tributario_id IN ({novos})"), {"fonte": FONTE})
    conn.execute(sa.text("DELETE FROM perfil_tributario WHERE fonte = :fonte"), {"fonte": FONTE})
    conn.execute(sa.text("UPDATE perfil_tributario SET vigente_ate = :fim, observacoes = NULL WHERE fonte = :fonte"),
                 {"fim": VIGENCIA[1], "fonte": FONTE_D075})
    with op.batch_alter_table("perfil_tributario") as tabela:
        tabela.drop_column("versao_legal")
        tabela.drop_column("item_lista_servico")
    for antigo, novo in TIPOS_D075.items():
        conn.execute(sa.text("UPDATE apuracao_comissao SET tipo_receita = :antigo WHERE tipo_receita = :novo"), {"novo": novo, "antigo": antigo})
    conn.execute(sa.text("UPDATE apuracao_comissao SET tipo_receita = 'SERVICO' WHERE tipo_receita IN ('IMPLEMENTATION', 'UNCLASSIFIED', "
                         "'CONSULTING', 'SUPPORT')"))
    op.create_table(
        "modelo_custo_infra", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("nome", sa.String(), nullable=False),
        sa.Column("vigente_de", sa.Date(), nullable=False), sa.Column("vigente_ate", sa.Date(), nullable=True),
        sa.Column("metodo", sa.String(), nullable=False), sa.Column("componentes", sa.JSON(), nullable=False),
        sa.Column("fonte", sa.String(), nullable=True), sa.Column("observacoes", sa.String(), nullable=True),
        sa.Column("criado_por", sa.String(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    with op.batch_alter_table("apuracao_comissao") as tabela:
        tabela.add_column(sa.Column("modelo_custo_infra_id", sa.Integer(), nullable=True))
        tabela.create_foreign_key("fk_apuracao_modelo_custo_infra", "modelo_custo_infra", ["modelo_custo_infra_id"], ["id"])
        tabela.create_index("ix_apuracao_comissao_modelo_custo_infra_id", ["modelo_custo_infra_id"])
        tabela.drop_column("custo_direto_ate")
        tabela.drop_column("meses_infra")
        tabela.drop_column("custo_infra_real")
    for nome_tabela in ("alerta_capacidade_infra", "custo_direto_infra", "uso_capacidade_infra", "componente_infra"):
        op.drop_table(nome_tabela)
    for nome in FRANQUIA_GOVERNO:
        conn.execute(sa.text("UPDATE plano SET franquia_contas_mes = 0 WHERE nome = :nome"), {"nome": nome})
    with op.batch_alter_table("plano") as tabela:
        tabela.drop_column("tier_infraestrutura")
