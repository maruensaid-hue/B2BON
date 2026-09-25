"""Registro de features, agentes e ferramentas de IA (Fase 4, §19, §72).

Toda chamada de IA declara uma `feature` registrada aqui: é ela que diz o
módulo (atribuição de custo), o agente, a classe de modelo e se o gatilho
é humano ou automático. Feature não registrada = chamada recusada — não
existe caminho de IA "anônimo".

Agentes do §19 ainda não implementados ficam com status PLANEJADO (não
aparecem como disponíveis). Ferramentas têm sensibilidade: READ, WRITE,
EXTERNAL_ACTION (sempre vira rascunho sob aprovação humana, §17) e
SENSITIVE_ACTION (nunca executada por agente).
"""

from dataclasses import dataclass, field
from enum import StrEnum

from app.contexts.intelligence.roteador import ClasseModelo


class Gatilho(StrEnum):
    USUARIO = "usuario"
    AUTOMATICO = "automatico"
    API = "api"


class StatusAgente(StrEnum):
    ATIVO = "ATIVO"
    PLANEJADO = "PLANEJADO"


class Sensibilidade(StrEnum):
    READ = "READ"
    WRITE = "WRITE"
    EXTERNAL_ACTION = "EXTERNAL_ACTION"
    SENSITIVE_ACTION = "SENSITIVE_ACTION"


@dataclass(frozen=True)
class Feature:
    nome: str
    modulo: str
    agente: str
    classe: ClasseModelo
    gatilho: Gatilho
    descricao: str
    conteudo_externo: bool = False  # prompt carrega texto de terceiro (§62)


@dataclass(frozen=True)
class Agente:
    id: str
    nome: str
    dominio: str
    status: StatusAgente
    ferramentas: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Ferramenta:
    nome: str
    sensibilidade: Sensibilidade
    modulo: str
    descricao: str


FEATURES: dict[str, Feature] = {
    f.nome: f
    for f in [
        Feature("network.agente_corporativo", "network", "corporate_ai_agent", ClasseModelo.C2, Gatilho.USUARIO,
                "Responde, sob aprovação, perguntas de outra empresa sobre a do tenant.", conteudo_externo=True),
        Feature("crm.meeting_brief", "crm", "meeting_agent", ClasseModelo.C2, Gatilho.USUARIO, "Preparação de reunião a partir do negócio."),
        Feature("intelligence.estrategia_venda", "predator", "sales_strategy_agent", ClasseModelo.C2, Gatilho.USUARIO, "Estratégia de venda para uma conta."),
        Feature("predator.enriquecimento_site", "predator", "research_agent", ClasseModelo.C2, Gatilho.USUARIO,
                "Sinais públicos a partir do site institucional.", conteudo_externo=True),
        Feature("predator.mensagem_cadencia", "predator", "cadence_agent", ClasseModelo.C2, Gatilho.USUARIO, "Rascunho de toque de cadência (vai para aprovação)."),
        Feature("predator.mensagem_indicacao", "predator", "relationship_agent", ClasseModelo.C2, Gatilho.AUTOMATICO, "Rascunho de pedido de indicação (vai para aprovação)."),
        Feature("predator.qualificacao", "predator", "qualification_agent", ClasseModelo.C2, Gatilho.AUTOMATICO,
                "Sugestão de resposta a mensagem de lead (não é enviada).", conteudo_externo=True),
        Feature("predator.resumo_reuniao", "predator", "meeting_intelligence_agent", ClasseModelo.C2, Gatilho.AUTOMATICO,
                "Resumo de transcrição de reunião para nota de CRM.", conteudo_externo=True),
        Feature("map.script_resgate_conta", "map", "remediation_agent", ClasseModelo.C2, Gatilho.USUARIO, "Mensagem de resgate para conta em risco."),
        Feature("map.script_resgate_tenant", "map", "remediation_agent", ClasseModelo.C2, Gatilho.USUARIO, "Resgate de tenant assinante (uso interno CyberFort)."),
        Feature("network.explicar_match", "network", "intent_agent", ClasseModelo.C1, Gatilho.USUARIO, "Explica o match entre uma necessidade e um fornecedor."),
        Feature("predator.sugerir_regra", "predator", "learning_agent", ClasseModelo.C1, Gatilho.USUARIO, "Sugere regra a partir de uma correção humana."),
        Feature("plataforma.amostra_comunicacao", "plataforma", "cadence_agent", ClasseModelo.C1, Gatilho.USUARIO, "Prévia do tom de comunicação."),
        Feature("opportunity.extracao_necessidades", "crm", "opportunity_agent", ClasseModelo.C2, Gatilho.USUARIO,
                "Sugere necessidades do cliente a partir de reunião/nota, com citação literal (vai para revisão).",
                conteudo_externo=True),
        Feature("plataforma.faq", "plataforma", "help_agent", ClasseModelo.C1, Gatilho.USUARIO, "Ajuda sobre como usar a plataforma."),
    ]
}

FERRAMENTAS: dict[str, Ferramenta] = {
    f.nome: f
    for f in [
        Ferramenta("brain.buscar", Sensibilidade.READ, "intelligence", "Busca no Corporate Brain do tenant."),
        Ferramenta("map.saude_conta", Sensibilidade.READ, "map", "Score de risco de uma conta."),
        Ferramenta("crm.listar_oportunidades", Sensibilidade.READ, "crm", "Negócios do tenant."),
        Ferramenta("predator.rascunho_mensagem", Sensibilidade.EXTERNAL_ACTION, "predator",
                   "Cria rascunho de mensagem na fila de aprovação (nunca envia)."),
        Ferramenta("crm.mover_estagio", Sensibilidade.WRITE, "crm", "Move negócio de estágio."),
        Ferramenta("plataforma.alterar_plano", Sensibilidade.SENSITIVE_ACTION, "plataforma", "Nunca executada por agente."),
    ]
}

AGENTES: dict[str, Agente] = {
    a.id: a
    for a in [
        Agente("corporate_ai_agent", "Agente Corporativo", "network", StatusAgente.ATIVO, ("brain.buscar",)),
        Agente("meeting_agent", "Meeting Agent", "crm", StatusAgente.ATIVO, ("crm.listar_oportunidades",)),
        Agente("sales_strategy_agent", "Sales Strategy Agent", "intelligence", StatusAgente.ATIVO, ("brain.buscar",)),
        Agente("research_agent", "Research Agent", "predator", StatusAgente.ATIVO),
        Agente("cadence_agent", "Cadence Agent", "predator", StatusAgente.ATIVO, ("predator.rascunho_mensagem",)),
        Agente("relationship_agent", "Relationship Agent", "predator", StatusAgente.ATIVO, ("predator.rascunho_mensagem",)),
        Agente("qualification_agent", "Qualification Agent", "predator", StatusAgente.ATIVO),
        Agente("meeting_intelligence_agent", "Meeting Intelligence Agent", "predator", StatusAgente.ATIVO),
        Agente("remediation_agent", "Remediation Agent", "map", StatusAgente.ATIVO, ("map.saude_conta",)),
        Agente("intent_agent", "Intent Agent", "network", StatusAgente.ATIVO),
        Agente("learning_agent", "Learning Agent", "intelligence", StatusAgente.ATIVO),
        Agente("help_agent", "Help Agent", "plataforma", StatusAgente.ATIVO),
        Agente("opportunity_agent", "Opportunity Agent", "intelligence", StatusAgente.ATIVO),
        # §19 — planejados (fases 9, 10, 12)
        Agente("icp_agent", "ICP Agent", "predator", StatusAgente.PLANEJADO),
        Agente("stakeholder_agent", "Stakeholder Agent", "intelligence", StatusAgente.PLANEJADO),
        Agente("pipeline_agent", "Pipeline Agent", "crm", StatusAgente.PLANEJADO),
        Agente("revenue_agent", "Revenue Agent", "map", StatusAgente.PLANEJADO),
        Agente("churn_intelligence_agent", "Churn Intelligence Agent", "map", StatusAgente.PLANEJADO),
        Agente("procurement_intelligence_agent", "Procurement Intelligence Agent", "procurement", StatusAgente.PLANEJADO),
        Agente("tender_analyzer", "Tender Analyzer", "bids", StatusAgente.PLANEJADO),
        Agente("tr_analyzer", "Term of Reference Analyzer", "bids", StatusAgente.PLANEJADO),
        Agente("bid_qualification_agent", "Bid Qualification Agent", "bids", StatusAgente.PLANEJADO),
        Agente("competitive_intelligence_agent", "Competitive Intelligence Agent", "bids", StatusAgente.PLANEJADO),
        Agente("contract_intelligence_agent", "Contract Intelligence Agent", "procurement", StatusAgente.PLANEJADO),
        Agente("procurement_planning_agent", "Procurement Planning Agent", "procurement", StatusAgente.PLANEJADO),
        Agente("supplier_intelligence_agent", "Supplier Intelligence Agent", "procurement", StatusAgente.PLANEJADO),
        Agente("procurement_risk_agent", "Procurement Risk Agent", "procurement", StatusAgente.PLANEJADO),
    ]
}


def obter_feature(nome: str) -> Feature:
    feature = FEATURES.get(nome)
    if feature is None:
        raise ValueError(f"Feature de IA não registrada: {nome}. Registre em app/contexts/intelligence/registro.py.")
    return feature


def agente_pode_usar(agente_id: str, ferramenta: str) -> bool:
    agente = AGENTES.get(agente_id)
    return bool(agente and agente.status == StatusAgente.ATIVO and ferramenta in agente.ferramentas)
