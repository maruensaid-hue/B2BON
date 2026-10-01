"""MAP Performance Comercial (D-080): constantes, códigos de política e valores iniciais aprovados pelo PO.

Nada aqui é lido diretamente pelos componentes: os valores iniciais semeiam as políticas versionadas (`politica_comissao`)
e as quotas (`quota_comercial`); depois disso, o que vale é sempre a versão ativa no banco (configurável e auditada).
"""

from enum import StrEnum

CODIGO_POLITICA_PERFORMANCE = "MAP_PERFORMANCE_POLICY"
CODIGO_POLITICA_COMISSAO_PRIVADA = "PRIVATE_RECURRING_COMMISSION"
CODIGO_CAMPANHA_VERAO = "SUMMER_SALES_CHALLENGE_2026"
PREFIXO_CAMPANHA = "CAMPAIGN:"


class Metrica(StrEnum):
    NEW_MRR = "NEW_MRR"


class Familia(StrEnum):
    SUITE = "SUITE"
    PREDATOR = "PREDATOR"
    BID_INTELLIGENCE = "BID_INTELLIGENCE"
    STRATEGIC_SOURCING = "STRATEGIC_SOURCING"
    MAP_CRM = "MAP_CRM"
    GOVERNMENT = "GOVERNMENT"
    NAO_CLASSIFICADA = "UNCLASSIFIED"


class Velocidade(StrEnum):
    FAST = "FAST"
    CORE = "CORE"
    STRATEGIC = "STRATEGIC"


class SituacaoCarteira(StrEnum):
    ADIMPLENTE = "CURRENT"
    INADIMPLENTE = "DELINQUENT"
    CANCELADO = "CANCELLED"


class Severidade(StrEnum):
    CRITICA = "CRITICAL"
    ALTA = "HIGH"
    MEDIA = "MEDIUM"
    INFO = "INFO"


# Ordem de prioridade: a primeira regra que casa classifica o plano (categoria, módulo contratado ou segmento).
POLITICA_PERFORMANCE_INICIAL: dict = {
    "fonte_new_mrr": "FIRST_PAYMENT",  # New MRR = 1ª mensalidade aprovada de um cliente novo do representante
    "cobertura": {"multiplo_padrao": 3.0, "dias_janela_forecast": 0},
    "funil_baseline": {  # taxas iniciais de planejamento (Out/26); recalculadas com dados reais (ver `aprendizado`)
        "contas_trabalhadas": 400, "contato_efetivo": 0.30, "reuniao": 0.35, "oportunidade_qualificada": 0.60,
        "proposta": 0.60, "fechamento": 0.33,
    },
    "aprendizado": {"janela_dias": 90, "amostra_minima": 20},
    "atividade": {
        "diaria": {"contas_trabalhadas": 20, "contatos_efetivos": 6, "reunioes": 2, "follow_ups": 8, "oportunidades_atualizadas_pct": 1.0},
        "semanal": {"contas_trabalhadas": 100, "contatos_efetivos": 30, "reunioes": 10, "oportunidades_qualificadas": 6,
                    "propostas_min": 3, "propostas_max": 4, "fechamentos_min": 1, "fechamentos_max": 2, "new_mrr": 1875.0},
    },
    "definicoes": {
        # "Conta trabalhada" = ICP validado + persona/contato alvo + ação comercial registrada por uma pessoa.
        # Disparos automáticos (atividade sem usuário) nunca contam: o MAP não premia spam.
        "tipos_acao_comercial": ["ligacao", "email", "whatsapp", "linkedin", "reuniao"],
        "tipos_contato_efetivo": ["ligacao", "reuniao"],
        "score_icp_minimo": 0.6,
        "dias_oportunidade_atualizada": 7,
        "dias_proposta_sem_atividade": 5,
        "dias_oportunidade_estagnada": 14,
    },
    "ticket_medio_baseline": 1750.0,
    "mix": {
        "alvo": {"SUITE": 0.50, "PREDATOR": 0.20, "BID_INTELLIGENCE": 0.15, "STRATEGIC_SOURCING": 0.10, "MAP_CRM": 0.05},
        "familias_alto_valor": ["SUITE", "BID_INTELLIGENCE", "STRATEGIC_SOURCING"],
        "alto_valor_minimo": 0.50,
    },
    "classificacao_planos": [
        {"familia": "GOVERNMENT", "segmento": "GOVERNMENT"},
        {"familia": "SUITE", "categoria": "suite"},
        {"familia": "STRATEGIC_SOURCING", "modulo": "sourcing"},
        {"familia": "BID_INTELLIGENCE", "modulo": "bids"},
        {"familia": "PREDATOR", "modulo": "predator"},
        {"familia": "MAP_CRM", "modulo": "crm"},
        {"familia": "MAP_CRM", "modulo": "map"},
    ],
    "familia_por_oferta": {},  # {oferta_id (CRM do operador): familia} — pipeline privado por produto
    "velocidade": {
        "por_familia": {"SUITE": "CORE", "PREDATOR": "FAST", "BID_INTELLIGENCE": "FAST", "STRATEGIC_SOURCING": "FAST",
                        "MAP_CRM": "FAST", "GOVERNMENT": "STRATEGIC", "UNCLASSIFIED": "CORE"},
        "dias": {"FAST": 15, "CORE": 45, "STRATEGIC": 180},
    },
    "governo": {
        "oportunidades_qualificadas_semana": 2,
        "estagio_nao_qualificado": "OPPORTUNITY_IDENTIFIED",  # aberta e além da identificação = qualificada
        "conta_na_quota_privada": False,  # pipeline governamental nunca compensa a quota privada
    },
    "alertas": {
        "atividade_alta_pct": 1.0, "ticket_baixo_pct": 0.70, "conversao_baixa_pct": 0.50, "risco_quota_pct": 0.80,
        "max_negocios_daily": 5,
    },
}

POLITICA_COMISSAO_PRIVADA_INICIAL: dict = {
    "taxa": 0.20,
    "gatilho": "PAYMENT_RECEIVED",  # só mensalidade efetivamente paga gera comissão (Commission Engine, D-074)
    "base": "NET_COMMISSIONABLE_MARGIN",  # D-074: a base continua a Margem Comissionável Líquida do recebimento
    "recorrente": True,
    "inadimplencia": {"ciclo_dias": 30, "tolerancia_dias": 10, "acao": "HOLD"},  # HOLD: comissão a pagar fica retida
    "cancelamento": {"acao": "STOP_FUTURE", "estorno_se_cancelado_em_dias": 0},
}

CAMPANHA_VERAO_INICIAL: dict = {
    "nome": "Summer Sales Challenge",
    "metrica": "NEW_MRR",
    "inicio": "2026-12-01",
    "fim": "2027-01-31",
    "meta_individual": 27500.0,
    "meta_equipe": 192500.0,
    "faixas": [  # bônus sobre a comissão das NOVAS vendas do período (nunca sobre a carteira histórica)
        {"de": 0.0, "bonus": 0.0}, {"de": 0.80, "bonus": 0.0}, {"de": 1.00, "bonus": 0.20},
        {"de": 1.20, "bonus": 0.35}, {"de": 1.50, "bonus": 0.50},
    ],
    "base_bonus": "COMMISSION_OF_NEW_SALES",
    "dias_comissao_apos_fim": 0,
    "elegibilidade": {"venda_em_cada_mes": True, "crm_atualizado_pct": 0.9, "carteira_adimplente": True, "bloqueados": {}},
}

# Quota individual de New MRR (Out/26–Mar/27) e o target gerencial de pipeline qualificado de outubro.
QUOTAS_INICIAIS = (("2026-10", 7500.0, 30000.0), ("2026-11", 10000.0, None), ("2026-12", 12500.0, None),
                   ("2027-01", 15000.0, None), ("2027-02", 17500.0, None), ("2027-03", 20000.0, None))
