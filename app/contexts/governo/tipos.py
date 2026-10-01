"""B2B ON Government (D-072): modelos de cobrança, componentes, gatilhos, estágios e valores iniciais.

Preço e AI Credits dos planos ficam na tabela `plano` (catálogo central). Aqui só ficam nomes de
conceito e a política inicial de comissão / o template inicial, que também nascem no banco pela
migração `d9e1f3a5b7c9` (o teste `test_governo_catalogo` confere que as duas cópias são iguais).
"""

from enum import StrEnum

SEGMENTO_GOVERNO = "GOVERNMENT"
CODIGO_POLITICA = "GOVERNMENT"
CODIGO_TEMPLATE_PROPOSTA = "PROPOSTA_GOVERNO"


class ModeloCobranca(StrEnum):
    MENSAL = "MONTHLY_SUBSCRIPTION"
    LICENCA_MAIS_ASSINATURA = "GOVERNMENT_LICENSE_PLUS_ANNUAL_SUBSCRIPTION"
    SO_ASSINATURA = "GOVERNMENT_ANNUAL_SUBSCRIPTION_ONLY"


MODELOS_GOVERNO = (ModeloCobranca.LICENCA_MAIS_ASSINATURA, ModeloCobranca.SO_ASSINATURA)


class Componente(StrEnum):
    LICENCA = "LICENSE"
    IMPLANTACAO = "IMPLEMENTATION"
    ASSINATURA_INICIAL = "INITIAL_ANNUAL_SUBSCRIPTION"
    RENOVACAO = "RENEWAL_ANNUAL_SUBSCRIPTION"
    SERVICOS = "ADDITIONAL_SERVICES"
    CREDITOS = "ADDITIONAL_AI_CREDITS"


RECORRENTES = frozenset({Componente.ASSINATURA_INICIAL, Componente.RENOVACAO})  # só estes entram no ARR
ADICIONAIS = (Componente.SERVICOS, Componente.CREDITOS)


class Gatilho(StrEnum):
    """Quando a comissão passa a ser devida. D-074: só o recebimento (PAYMENT_RECEIVED), proporcional a cada parcela;
    a comissão também precisa dos parâmetros de custo para chegar a PAYABLE."""

    PAGAMENTO_RECEBIDO = "PAYMENT_RECEIVED"


ESTAGIOS = (
    "OPPORTUNITY_IDENTIFIED", "QUALIFIED_GOVERNMENT_OPPORTUNITY", "PROCUREMENT_SIGNAL", "RFP_EDITAL_TR", "PROPOSAL",
    "EVALUATION", "AWARD_ADJUDICATION", "CONTRACT", "BOOKING", "PAYMENT", "COMMISSION_EVENT", "LOST",
)
ESTAGIOS_FECHADOS = frozenset({"CONTRACT", "BOOKING", "PAYMENT", "COMMISSION_EVENT", "LOST"})

# Entitlements Government (D-075, OI-024). Cada valor vive num lugar só do catálogo central (tabela `plano`):
# - internal_users → `max_usuarios` (o mesmo limite de assentos que a plataforma já aplica);
# - crm, map, predator, bid_intelligence → `modulos_contratados` (o acesso real aos módulos);
# - public_procurement → nível no JSON, liberado só com "procurement" em `modulos_contratados`;
# - api_access → `permite_api_parceiros`;
# - demais → JSON `entitlements` (CHAVES_ENTITLEMENT). Valor None = "conforme contrato".
ORDEM_ENTITLEMENTS = (
    "internal_users", "administrative_units", "storage_gb", "operational_retention_months", "crm", "map", "predator",
    "bid_intelligence", "public_procurement", "business_network", "corporate_brain", "api_access", "sso", "support_sla", "onboarding",
)
MODULO_POR_ENTITLEMENT = {"crm": "crm", "map": "map", "predator": "predator", "bid_intelligence": "bids"}
CHAVES_ENTITLEMENT = (
    "administrative_units", "storage_gb", "operational_retention_months", "public_procurement", "business_network",
    "corporate_brain", "sso", "support_sla", "onboarding",
)
NIVEIS_PUBLIC_PROCUREMENT = ("BASIC", "FULL")
VALORES_SSO = (True, False, "OPTIONAL")
SLAS_SUPORTE = ("BUSINESS_HOURS_8X5", "PRIORITY_BUSINESS_HOURS_8X5", "CRITICAL_BUSINESS_HOURS_8X5")
ONBOARDINGS = ("STANDARD", "ADVANCED", "DEDICATED")

POLITICA_INICIAL = {
    "gatilho": Gatilho.PAGAMENTO_RECEBIDO.value,
    "componentes": {
        Componente.LICENCA.value: {"comissionavel": True, "taxa": 0.20},
        Componente.ASSINATURA_INICIAL.value: {"comissionavel": True, "taxa": 0.20},
        Componente.RENOVACAO.value: {"comissionavel": True, "taxa": 0.10},
        Componente.IMPLANTACAO.value: {"comissionavel": False, "taxa": 0.20},
        Componente.SERVICOS.value: {"comissionavel": False, "taxa": None},
        Componente.CREDITOS.value: {"comissionavel": False, "taxa": None},
    },
}

# D-073: serviços e AI Credits adicionais comissionáveis a 10% (migração e1f3a5b7c9d2, versão seguinte da política)
POLITICA_ATUAL = {
    "gatilho": POLITICA_INICIAL["gatilho"],
    "componentes": {
        **POLITICA_INICIAL["componentes"],
        Componente.SERVICOS.value: {"comissionavel": True, "taxa": 0.10},
        Componente.CREDITOS.value: {"comissionavel": True, "taxa": 0.10},
    },
}

TEMPLATE_PROPOSTA_INICIAL = (
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
MARCADORES_TEMPLATE = ("plano", "entidade", "referencia", "licenca", "implantacao", "assinatura", "contratacao_inicial", "creditos")
