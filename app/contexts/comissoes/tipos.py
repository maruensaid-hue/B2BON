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

# Componentes do Infrastructure Cost Model
COMPONENTES_INFRA = {
    "PERCENTUAL": "PERCENTAGE",  # {"percentual": 0.05} sobre a receita recebida
    "FIXO_POR_RECEBIMENTO": "FIXED",  # {"valor": 50.0} por recebimento
    "POR_TENANT": "TENANT",  # {"percentuais": {"tenant": 0.03}, "padrao": 0.05 | null}
    "POR_PRODUTO": "PRODUCT",  # {"percentuais": {"GOVERNMENT": 0.04, "B2B ON Government Professional": 0.03}, "padrao": ...}
    "USO_IA": "USAGE",  # {"janela_dias": 30}: custo real de IA do tenant (ledger), sem contar duas vezes
}
