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
    CUSTO_INFRA = "INFRASTRUCTURE_COST"  # pool vazio, componente sem valor, plano sem tier
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


# Classificação da receita para o Tax Profile (natureza da receita, não alíquota). D-076: tipos separados — a regra
# fiscal de cada um vem só do Tax Profile.
class TipoReceita(StrEnum):
    LICENCA_SOFTWARE = "SOFTWARE_LICENSE"
    SAAS = "SAAS_SUBSCRIPTION"
    IMPLANTACAO = "IMPLEMENTATION"
    CONSULTORIA = "CONSULTING"
    SUPORTE = "SUPPORT"


RECEITA_SAAS = TipoReceita.SAAS.value
TIPOS_RECEITA = tuple(t.value for t in TipoReceita)
# Padrão por componente Government. Serviço adicional não tem padrão: a classificação vem do componente
# (implantação, consultoria ou suporte); sem ela, a apuração aguarda o Tax Profile.
TIPO_RECEITA_POR_COMPONENTE = {
    "LICENSE": TipoReceita.LICENCA_SOFTWARE.value,
    "IMPLEMENTATION": TipoReceita.IMPLANTACAO.value,
    "ADDITIONAL_SERVICES": None,
    "INITIAL_ANNUAL_SUBSCRIPTION": RECEITA_SAAS,
    "RENEWAL_ANNUAL_SUBSCRIPTION": RECEITA_SAAS,
    "ADDITIONAL_AI_CREDITS": RECEITA_SAAS,
}
RECEITA_NAO_CLASSIFICADA = "UNCLASSIFIED"
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


class SituacaoReforma(StrEnum):
    """CBS/IBS de 2026: a situação efetiva é registrada pela administração/contabilidade."""

    COMPENSADO = "COMPENSATED"
    DISPENSADO = "WAIVED_BY_COMPLIANCE"
    DEVIDO = "PAYABLE"
    PENDENTE = "PENDING_COMPLIANCE_CONFIRMATION"


# Infrastructure Cost Pool (D-076). Fornecedores são cadastrados; aqui só os nomes de conceito.
CATEGORIAS_INFRA = (
    "HOSTING", "DATABASE", "STORAGE", "MONITORING", "APIS", "DATA_PROVIDER", "EMAIL", "WHATSAPP", "SECURITY",
    "OBSERVABILITY", "BACKUP", "THIRD_PARTY", "AI", "OTHER",
)
CICLOS_COBRANCA = {"MONTHLY": 1, "QUARTERLY": 3, "ANNUAL": 12}


class PoliticaCustoInfra(StrEnum):
    PLANO_MAXIMO = "MAX_CONTRACTED_PLAN"  # provisionado = custo integral do plano de referência (conservador)
    CUSTO_REAL = "ACTUAL_COST"  # provisionado = custo real informado


class MetodoAlocacao(StrEnum):
    PONDERADA = "WEIGHTED"  # pool ÷ unidades ponderadas × peso do tier do tenant
    DIRETA = "DIRECT"  # custo medido por tenant (o restante do plano volta ao pool ponderado)


class Contabilizacao(StrEnum):
    INFRAESTRUTURA = "INFRASTRUCTURE"
    CUSTO_IA = "AI_COST"  # já contado no custo de IA do FinOps: nunca entra de novo como infraestrutura


class StatusCapacidade(StrEnum):
    NORMAL = "NORMAL"
    ATENCAO = "ATTENTION"
    REVISAR = "REVIEW"
    CRITICO = "CRITICAL"
    ESGOTADA = "CAPACITY_REACHED"


MENSAGENS_CAPACIDADE = {
    StatusCapacidade.REVISAR.value: "Revisar capacidade e condições comerciais do fornecedor.",
    StatusCapacidade.CRITICO.value: "Capacidade próxima do limite. Avaliar upgrade, contrato Enterprise, desconto por volume ou "
                                    "parceria estratégica.",
    StatusCapacidade.ESGOTADA.value: "Contracted capacity reached.",
}
TIERS_INFRA = ("ENTRY", "DEPARTMENT", "PROFESSIONAL", "ENTERPRISE")

# Política de infraestrutura (D-076), versionada em `politica_comissao`: pesos por tier, limiares de capacidade e a base
# de custo da comissão. Valores iniciais do PO; mudar = nova versão auditada.
CODIGO_POLITICA_INFRA = "INFRASTRUCTURE_COST_POLICY"
POLITICA_INFRA_INICIAL = {
    "pesos": {"ENTRY": 1.0, "DEPARTMENT": 1.0, "PROFESSIONAL": 2.0, "ENTERPRISE": 4.0},
    "limiares": {"ATTENTION": 0.70, "REVIEW": 0.80, "CRITICAL": 0.90, "CAPACITY_REACHED": 1.0},
    "custo_comissao": "PROVISIONED",
}
# Receita que remunera a operação de um período (o custo de infraestrutura do tenant é atribuído a ela, uma vez por mês
# de operação). Licença, implantação e adicionais não cobrem meses de operação.
COMPONENTES_OPERACIONAIS = ("INITIAL_ANNUAL_SUBSCRIPTION", "RENEWAL_ANNUAL_SUBSCRIPTION")

# Commission Policy da margem (D-075). Impostos e infraestrutura atribuíveis são sempre deduzidos (D-074); o custo de IA
# só entra na Margem Comissionável Líquida se a política disser explicitamente — existir no FinOps não basta.
CODIGO_POLITICA_MARGEM = "NET_COMMISSIONABLE_MARGIN"
POLITICA_MARGEM_INICIAL = {"deduzir_custo_ia": False}
