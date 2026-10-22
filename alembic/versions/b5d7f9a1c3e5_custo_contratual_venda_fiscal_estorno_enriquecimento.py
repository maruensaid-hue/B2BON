"""Enriquecimento: custo contratual do provedor, pagamentos ao provedor, nota fiscal, conciliação da venda e estorno manual.

* Precisão: custos e preços por crédito passam a 12 casas (o custo contratual USD 600 ÷ 6.800 × R$ 6,00 é uma dízima: R$ 0,529411764706). Só amplia a coluna.
* Novas tabelas: `enriquecimento_custo_provedor` (versionada e aprovada), `enriquecimento_pagamento_provedor` (append-only), `enriquecimento_nota_fiscal`
  e `enriquecimento_estorno_compra`. Novas colunas (nulas) em `enriquecimento_compra` para a conciliação e a contestação.
* Dados inseridos, todos informados pelo PO: a base econômica do provedor de contatos (USD 600/mês, 81.600 créditos/ano, câmbio de planejamento R$ 6,00), aprovada MAS COM O
  CONTRATO NÃO VALIDADO (a validação é ato humano: a pesquisa de decisores continua bloqueada até ela), e o orçamento global de 6.800 créditos/mês (a capacidade
  equivalente ao teto de USD 600), só se ainda não houver nenhum orçamento do provedor.
* Dado removido: o lote de compra pontual de 400 créditos por R$ 269,94, semeado pela migração anterior, que o PO mandou desconsiderar. Só é removido se
  nenhuma política o referencia (se alguma referenciar, permanece e o fato fica visível na tela de administração).

Downgrade: remove as tabelas e as colunas novas e volta a precisão; NÃO recria o lote desconsiderado. Notas, pagamentos ao provedor e estornos são histórico
financeiro: faça cópia antes de reverter em ambiente com uso.

Revision ID: b5d7f9a1c3e5
Revises: a4c6e8b0d2f4
Create Date: 2026-10-21
"""
from datetime import datetime
from decimal import Decimal

import sqlalchemy as sa
from alembic import op

from app.contexts.enriquecimento.matriz_dados import (
    ALERTA_ORCAMENTO_PERCENTUAL,
    APROVADOR_CUSTO,
    CUSTO_CONTATOS,
    LOTE_DESCONSIDERADO,
    MOTIVO_CUSTO,
    ORCAMENTO_CONTATOS_CREDITOS_MES,
)

revision = "b5d7f9a1c3e5"
down_revision = "a4c6e8b0d2f4"
branch_labels = None
depends_on = None

_AMPLIAR = (
    ("enriquecimento_lote_compra", ("custo_total_brl", "custo_unitario_brl")),
    ("enriquecimento_politica_provedor", ("custo_unitario_brl", "preco_unitario_brl")),
    ("enriquecimento_movimento", ("custo_unitario_brl", "preco_unitario_brl", "custo_total_brl", "valor_venda_brl")),
)


def _tipo(tabela: str, coluna: str, casas: int) -> None:
    anulavel = tabela != "enriquecimento_lote_compra"
    with op.batch_alter_table(tabela) as lote:
        lote.alter_column(coluna, type_=sa.Numeric(24 if casas == 12 else 18, casas), existing_nullable=anulavel)


def upgrade() -> None:
    for tabela, colunas in _AMPLIAR:
        for coluna in colunas:
            _tipo(tabela, coluna, 12)

    for nome, tipo in (("valor_pago_brl", sa.Numeric(14, 2)), ("taxa_pagamento_brl", sa.Numeric(14, 2)), ("valor_liquido_brl", sa.Numeric(14, 2)),
                       ("status_pagamento_externo", sa.String()), ("contestacao_status", sa.String()), ("contestado_em", sa.DateTime())):
        op.add_column("enriquecimento_compra", sa.Column(nome, tipo, nullable=True))

    op.create_table(
        "enriquecimento_custo_provedor",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provedor", sa.String(), nullable=False),
        sa.Column("versao", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("custo_mensal_usd", sa.Numeric(18, 4), nullable=False),
        sa.Column("creditos_anuais", sa.Integer(), nullable=False),
        sa.Column("creditos_mensais", sa.Integer(), nullable=False),
        sa.Column("cambio_planejamento_brl", sa.Numeric(12, 6), nullable=False),
        sa.Column("custo_unitario_usd", sa.Numeric(24, 12), nullable=False),
        sa.Column("custo_unitario_brl", sa.Numeric(24, 12), nullable=False),
        sa.Column("custo_mensal_brl", sa.Numeric(18, 2), nullable=False),
        sa.Column("motivo", sa.String(), nullable=True),
        sa.Column("criado_por", sa.String(), nullable=True),
        sa.Column("aprovado_por", sa.String(), nullable=True),
        sa.Column("aprovado_em", sa.DateTime(), nullable=True),
        sa.Column("valido_de", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("valido_ate", sa.DateTime(), nullable=True),
        sa.Column("contrato_validado_por", sa.String(), nullable=True),
        sa.Column("contrato_validado_em", sa.DateTime(), nullable=True),
        sa.Column("contrato_checklist", sa.JSON(), nullable=True),
        sa.Column("contrato_evidencia", sa.String(), nullable=True),
        sa.Column("saldo_transferivel", sa.Boolean(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("provedor", "versao", name="uq_enriq_custo_provedor_versao"),
    )
    op.create_index("ix_enriquecimento_custo_provedor_provedor", "enriquecimento_custo_provedor", ["provedor"])
    op.create_table(
        "enriquecimento_pagamento_provedor",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provedor", sa.String(), nullable=False),
        sa.Column("referencia", sa.String(), nullable=False),
        sa.Column("periodo", sa.String(), nullable=False),
        sa.Column("valor_usd", sa.Numeric(18, 4), nullable=False),
        sa.Column("taxa_cambio_efetiva", sa.Numeric(12, 6), nullable=False),
        sa.Column("encargos_brl", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("valor_brl_total", sa.Numeric(18, 2), nullable=False),
        sa.Column("pago_em", sa.DateTime(), nullable=False),
        sa.Column("observacao", sa.String(), nullable=True),
        sa.Column("registrado_por", sa.String(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("provedor", "referencia", name="uq_enriq_pagamento_provedor_referencia"),
    )
    op.create_index("ix_enriquecimento_pagamento_provedor_provedor", "enriquecimento_pagamento_provedor", ["provedor"])
    op.create_index("ix_enriquecimento_pagamento_provedor_periodo", "enriquecimento_pagamento_provedor", ["periodo"])
    op.create_table(
        "enriquecimento_nota_fiscal",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("compra_id", sa.Integer(), sa.ForeignKey("enriquecimento_compra.id"), nullable=False, unique=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="PENDENTE"),
        sa.Column("provedor_fiscal", sa.String(), nullable=True),
        sa.Column("numero", sa.String(), nullable=True),
        sa.Column("chave_acesso", sa.String(), nullable=True),
        sa.Column("referencia_externa", sa.String(), nullable=True),
        sa.Column("url_documento", sa.String(), nullable=True),
        sa.Column("valor_brl", sa.Numeric(14, 2), nullable=False),
        sa.Column("tentativas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("erro", sa.String(), nullable=True),
        sa.Column("emitida_em", sa.DateTime(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_enriquecimento_nota_fiscal_tenant_id", "enriquecimento_nota_fiscal", ["tenant_id"])
    op.create_table(
        "enriquecimento_estorno_compra",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("compra_id", sa.Integer(), sa.ForeignKey("enriquecimento_compra.id"), nullable=False),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("tipo", sa.String(), nullable=False),
        sa.Column("creditos_solicitados", sa.Integer(), nullable=False),
        sa.Column("justificativa", sa.String(), nullable=False),
        sa.Column("evidencia", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="SOLICITADO"),
        sa.Column("solicitado_por", sa.String(), nullable=False),
        sa.Column("solicitado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("decidido_por", sa.String(), nullable=True),
        sa.Column("decidido_em", sa.DateTime(), nullable=True),
        sa.Column("motivo_decisao", sa.String(), nullable=True),
        sa.Column("creditos_revertidos", sa.Integer(), nullable=True),
        sa.Column("creditos_ja_consumidos", sa.Integer(), nullable=True),
        sa.Column("movimento_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_enriquecimento_estorno_compra_compra_id", "enriquecimento_estorno_compra", ["compra_id"])
    op.create_index("ix_enriquecimento_estorno_compra_tenant_id", "enriquecimento_estorno_compra", ["tenant_id"])

    conexao = op.get_bind()
    agora = datetime(2026, 10, 21)

    # 1) Remove o lote pontual desconsiderado pelo PO, se nenhuma política o referencia.
    lote = sa.table("enriquecimento_lote_compra", sa.column("id", sa.Integer), sa.column("referencia", sa.String))
    politica = sa.table("enriquecimento_politica_provedor", sa.column("lote_compra_id", sa.Integer))
    alvo = conexao.execute(sa.select(lote.c.id).where(lote.c.referencia == LOTE_DESCONSIDERADO)).first()
    if alvo is not None and conexao.execute(sa.select(sa.func.count()).select_from(politica).where(politica.c.lote_compra_id == alvo[0])).scalar() == 0:
        conexao.execute(lote.delete().where(lote.c.id == alvo[0]))

    # 2) Base econômica do provedor de contatos (aprovada pelo PO; contrato NÃO validado: a pesquisa continua bloqueada até um humano validar).
    custo = sa.table(
        "enriquecimento_custo_provedor",
        sa.column("provedor", sa.String), sa.column("versao", sa.Integer), sa.column("custo_mensal_usd", sa.Numeric), sa.column("creditos_anuais", sa.Integer),
        sa.column("creditos_mensais", sa.Integer), sa.column("cambio_planejamento_brl", sa.Numeric), sa.column("custo_unitario_usd", sa.Numeric),
        sa.column("custo_unitario_brl", sa.Numeric), sa.column("custo_mensal_brl", sa.Numeric), sa.column("motivo", sa.String), sa.column("criado_por", sa.String),
        sa.column("aprovado_por", sa.String), sa.column("aprovado_em", sa.DateTime), sa.column("valido_de", sa.DateTime),
    )
    existe_custo = conexao.execute(sa.select(sa.func.count()).select_from(custo).where(custo.c.provedor == CUSTO_CONTATOS["provedor"])).scalar()
    if not existe_custo:
        usd, cambio = Decimal(CUSTO_CONTATOS["custo_mensal_usd"]), Decimal(CUSTO_CONTATOS["cambio_planejamento_brl"])
        mensais = CUSTO_CONTATOS["creditos_anuais"] // 12
        casas = Decimal("0.000000000001")
        op.bulk_insert(custo, [{
            "provedor": CUSTO_CONTATOS["provedor"], "versao": 1, "custo_mensal_usd": usd, "creditos_anuais": CUSTO_CONTATOS["creditos_anuais"], "creditos_mensais": mensais,
            "cambio_planejamento_brl": cambio, "custo_unitario_usd": (usd / mensais).quantize(casas), "custo_unitario_brl": (usd * cambio / mensais).quantize(casas),
            "custo_mensal_brl": (usd * cambio).quantize(Decimal("0.01")), "motivo": MOTIVO_CUSTO, "criado_por": "migracao", "aprovado_por": APROVADOR_CUSTO,
            "aprovado_em": agora, "valido_de": agora,
        }])

    # 3) Orçamento global equivalente ao teto de USD 600, só se ainda não existir nenhum orçamento do provedor.
    orcamento = sa.table(
        "enriquecimento_orcamento_global",
        sa.column("provedor", sa.String), sa.column("versao", sa.Integer), sa.column("limite_creditos", sa.Integer), sa.column("alerta_percentual", sa.Integer),
        sa.column("motivo", sa.String), sa.column("criado_por", sa.String), sa.column("aprovado_por", sa.String), sa.column("aprovado_em", sa.DateTime),
        sa.column("valido_de", sa.DateTime),
    )
    if not conexao.execute(sa.select(sa.func.count()).select_from(orcamento).where(orcamento.c.provedor == CUSTO_CONTATOS["provedor"])).scalar():
        op.bulk_insert(orcamento, [{
            "provedor": CUSTO_CONTATOS["provedor"], "versao": 1, "limite_creditos": ORCAMENTO_CONTATOS_CREDITOS_MES, "alerta_percentual": ALERTA_ORCAMENTO_PERCENTUAL,
            "motivo": MOTIVO_CUSTO, "criado_por": "migracao", "aprovado_por": APROVADOR_CUSTO, "aprovado_em": agora, "valido_de": agora,
        }])


def downgrade() -> None:
    conexao = op.get_bind()
    orcamento = sa.table("enriquecimento_orcamento_global", sa.column("criado_por", sa.String), sa.column("motivo", sa.String))
    conexao.execute(orcamento.delete().where(sa.and_(orcamento.c.criado_por == "migracao", orcamento.c.motivo == MOTIVO_CUSTO)))
    for tabela in ("enriquecimento_estorno_compra", "enriquecimento_nota_fiscal", "enriquecimento_pagamento_provedor", "enriquecimento_custo_provedor"):
        op.drop_table(tabela)
    with op.batch_alter_table("enriquecimento_compra") as lote:
        for nome in ("contestado_em", "contestacao_status", "status_pagamento_externo", "valor_liquido_brl", "taxa_pagamento_brl", "valor_pago_brl"):
            lote.drop_column(nome)
    for tabela, colunas in reversed(_AMPLIAR):
        for coluna in colunas:
            _tipo(tabela, coluna, 8)
