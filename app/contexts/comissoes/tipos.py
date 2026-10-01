"""Commission Engine (D-074): nomes de conceito. Nenhuma alíquota, custo ou taxa fica aqui — tudo é parâmetro."""

from enum import StrEnum


class Status(StrEnum):
    """Ciclo da comissão. RATE_DEFINED é a venda comissionável ainda não recebida (visão do contrato, sem linha)."""

    RATE_DEFINED = "RATE_DEFINED"
    AGUARDANDO = "AWAITING_COST_PARAMETERS"
    CALCULADA = "CALCULATED"
    PROVISIONADA = "ACCRUED"
    PAGAVEL = "PAYABLE"
    PAGA = "PAID"
    FALHOU = "FAILED"
    ESTORNADA = "REVERSED"
    COMPENSAR = "CLAWBACK_PENDING"


class Faltante(StrEnum):
    PERFIL_TRIBUTARIO = "TAX_PROFILE"
    CUSTO_INFRA = "INFRASTRUCTURE_COST"
    CAMBIO = "FX_RATE"  # custo de IA em USD sem cotação aplicável (OI-018)


# commission_amount_status: por que o valor da comissão ainda não existe (na ordem de prioridade abaixo)
STATUS_VALOR = {
    Faltante.CUSTO_INFRA.value: "AWAITING_INFRASTRUCTURE_COST",
    Faltante.PERFIL_TRIBUTARIO.value: "AWAITING_TAX_PROFILE",
    Faltante.CAMBIO.value: "AWAITING_FX_RATE",
}


class Origem(StrEnum):
    PAGAMENTO_LICENCA = "PAGAMENTO_LICENCA"
    RECEBIMENTO_GOVERNO = "RECEBIMENTO_GOVERNO"


# Classificação da receita para o Tax Profile (natureza da receita, não alíquota)
RECEITA_SAAS = "SAAS"
TIPO_RECEITA_POR_COMPONENTE = {
    "LICENSE": "LICENCA_SOFTWARE",
    "IMPLEMENTATION": "SERVICO",
    "ADDITIONAL_SERVICES": "SERVICO",
    "INITIAL_ANNUAL_SUBSCRIPTION": RECEITA_SAAS,
    "RENEWAL_ANNUAL_SUBSCRIPTION": RECEITA_SAAS,
    "ADDITIONAL_AI_CREDITS": RECEITA_SAAS,
}
QUALQUER = "*"


class Tributo(StrEnum):
    """Tributos que o Tax Engine calcula individualmente (D-075)."""

    IRPJ = "IRPJ"
    IRPJ_ADICIONAL = "IRPJ_ADDITIONAL"
    CSLL = "CSLL"
    PIS = "PIS"
    COFINS = "COFINS"
    ISS = "ISS"
    CBS = "CBS"
    IBS = "IBS"
    OUTRO = "OTHER_TAX"


class BaseTributo(StrEnum):
    RECEITA = "RECEITA"  # alíquota × receita recebida (PIS/COFINS cumulativos, ISS)
    PRESUNCAO = "PRESUNCAO"  # receita × percentual de presunção do tipo de receita → × alíquota (IRPJ, CSLL no Presumido)
    PRESUNCAO_EXCEDENTE = "PRESUNCAO_EXCEDENTE"  # adicional de IRPJ: só a base presumida acima do limite do período
    TESTE_REFORMA = "TESTE_REFORMA"  # CBS/IBS de 2026: alíquota-teste informativa; só entra o imposto de caixa efetivo


PERIODOS_APURACAO = {"MENSAL": 1, "TRIMESTRAL": 3, "ANUAL": 12}
STATUS_CONFORMIDADE = ("A_CONFIRMAR", "CUMPRIDA", "PENDENTE", "NAO_APLICAVEL")

# Infrastructure Cost Model (D-075): cada componente é uma categoria de custo alocada por um método.
CATEGORIAS_INFRA = (
    "cloud_cost", "database_cost", "storage_cost", "network_cost", "observability_cost", "third_party_cost",
    "allocated_ai_infrastructure_cost",
)
CATEGORIA_IA = "allocated_ai_infrastructure_cost"
METODOS_INFRA = {
    "FIXED": "valor fixo por recebimento — {\"valor\": 50.0}",
    "PERCENTAGE": "percentual da receita recebida — {\"percentual\": 0.05} ou {\"percentuais\": {produto|segmento: pct}, \"padrao\": pct}",
    "PER_TENANT": "valor por recebimento conforme o tenant — {\"valores\": {tenant_id: valor}, \"padrao\": valor}",
    "PER_USER": "valor por usuário ativo do tenant, por recebimento — {\"valor_por_usuario\": 2.5}",
    "USAGE_BASED": "custo real medido (só IA: ledger do AI Gateway, convertido pela cotação) — {\"janela_dias\": 30}",
}
METODO_HIBRIDO = "HYBRID"

# Commission Policy da margem (D-075). Impostos e infraestrutura atribuíveis são sempre deduzidos (D-074); o custo de IA
# só entra na Margem Comissionável Líquida se a política disser explicitamente — existir no FinOps não basta.
CODIGO_POLITICA_MARGEM = "NET_COMMISSIONABLE_MARGIN"
POLITICA_MARGEM_INICIAL = {"deduzir_custo_ia": False}
