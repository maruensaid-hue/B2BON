"""Workflow e ruleset do lado comprador (S4, D-055).

Fonte única do ciclo do processo de contratação (§38) e das regras da
Lei 14.133 usadas pelos sinais de risco e pela pesquisa de preços.
Reproduz o comportamento anterior à S4: qualquer etapa por mudança de
status (a aprovação de demanda e de plano segue pela ação de aprovar).

Parâmetros: o padrão vale para todos; `dias_alerta_contrato` e
`limite_fragmentacao` podem ser configurados por órgão (`orgao.parametros`).
`limite_fragmentacao` não tem padrão: sem configuração, o sinal fica sem
avaliação (UNKNOWN), nunca com um limite inventado.
"""

from datetime import date

from app.contexts.sourcing.contract import ruleset, tipos, workflow

ESTADOS = (
    "PLANEJAMENTO", "ESTUDOS_TECNICOS", "TERMO_REFERENCIA", "PESQUISA_PRECOS", "APROVACAO", "PUBLICADO",
    "SELECAO", "HOMOLOGADO", "CONTRATADO", "FRACASSADO", "CANCELADO",
)

PROCESSO = workflow.registrar(workflow.Workflow(
    codigo="PUBLIC_PROCUREMENT_BUY@1", lado=tipos.Lado.COMPRA, estados=ESTADOS, inicial="PLANEJAMENTO",
    finais=("CONTRATADO", "FRACASSADO", "CANCELADO"), transicoes=tuple(workflow.Transicao(e, "status") for e in ESTADOS),
))

LEI_14133 = ruleset.registrar(ruleset.Ruleset(
    codigo="PUBLIC_PROCUREMENT_BR_14133@1",
    descricao="Contratação pública brasileira (Lei 14.133/2021). Os parâmetros são padrões analíticos do B2B ON, não limites legais.",
    fonte="Lei nº 14.133, de 1º de abril de 2021 (Lei de Licitações e Contratos Administrativos)",
    vigente_desde=date(2021, 4, 1),  # art. 194: vigor na data da publicação
    # documento que o processo deveria ter a partir de cada etapa (Missing Documentation)
    documentos_esperados={
        "TERMO_REFERENCIA": ("ETP",),
        "PESQUISA_PRECOS": ("ETP", "TR"),
        "APROVACAO": ("ETP", "TR", "PESQUISA_PRECO"),
        "PUBLICADO": ("ETP", "TR", "PESQUISA_PRECO", "EDITAL"),
    },
    parametros={
        "dias_alerta_contrato": 120,   # contrato continuado sem sucessor a N dias do fim
        "desvio_orcamento": 0.2,       # processo acima do PCA em mais de 20%
        "desvio_alerta_preco": 0.30,   # cotação 30% acima/abaixo da mediana
        "limite_fragmentacao": None,   # depende do regime do órgão: sem padrão
    },
))
LADO = tipos.Lado.COMPRA
workflow.vincular(LADO, tipos.Segmento.PUBLICO, PROCESSO, LEI_14133)


def classificar(modalidade: str | None) -> tuple[tipos.Segmento, str]:
    """Modalidade do processo → (segmento, tipo de processo). O comprador de hoje é só o público."""
    return tipos.Segmento.PUBLICO, modalidade if modalidade in tipos.TIPOS_PROCESSO else "PUBLIC_TENDER"


def configuracao(modalidade: str | None) -> tuple[workflow.Workflow, ruleset.Ruleset | None]:
    return workflow.resolver(LADO, *classificar(modalidade))


def de(modalidade: str | None) -> workflow.Workflow:
    return configuracao(modalidade)[0]


# --- Enterprise Strategic Sourcing (Phase E, D-065): comprador privado --------------------------------
# Um fluxo por natureza de processo (§21), escolhido pelo vínculo (lado, segmento, tipo) — sem `if rfq`.
# Aprovação humana antes da adjudicação: ação `aprovacao` (pedido → EM_APROVACAO; decisão → ADJUDICADO ou volta).
T = workflow.Transicao
_MENSAGENS_EMPRESA = {
    "aprovacao": "A adjudicação passa pela aprovação: solicite e um administrador decide.",
    "contrato": "Registre o contrato depois da adjudicação aprovada.",
}
_ABERTOS = frozenset({"RASCUNHO", "PUBLICADO", "RECEBENDO_PROPOSTAS", "EM_AVALIACAO", "SHORTLIST", "EM_NEGOCIACAO", "EM_APROVACAO"})

SOURCING_EMPRESA = workflow.registrar(workflow.Workflow(
    codigo="ENTERPRISE_SOURCING_BUY@1", lado=tipos.Lado.COMPRA, inicial="RASCUNHO",
    estados=("RASCUNHO", "PUBLICADO", "RECEBENDO_PROPOSTAS", "EM_AVALIACAO", "SHORTLIST", "EM_NEGOCIACAO", "EM_APROVACAO",
             "ADJUDICADO", "CONTRATADO", "CANCELADO"),
    finais=("CONTRATADO", "CANCELADO"), mensagens=_MENSAGENS_EMPRESA,
    transicoes=(
        T("PUBLICADO", "status", frozenset({"RASCUNHO"})),
        T("RECEBENDO_PROPOSTAS", "status", frozenset({"PUBLICADO"})),
        T("EM_AVALIACAO", "status", frozenset({"RECEBENDO_PROPOSTAS", "EM_NEGOCIACAO", "SHORTLIST"})),
        T("SHORTLIST", "status", frozenset({"EM_AVALIACAO"})),
        T("EM_NEGOCIACAO", "status", frozenset({"EM_AVALIACAO", "SHORTLIST"})),
        T("CANCELADO", "status", _ABERTOS),
        T("EM_APROVACAO", "aprovacao", frozenset({"EM_AVALIACAO", "SHORTLIST", "EM_NEGOCIACAO"})),
        T("ADJUDICADO", "aprovacao", frozenset({"EM_APROVACAO"})),
        T("EM_AVALIACAO", "aprovacao", frozenset({"EM_APROVACAO"})),  # aprovação recusada volta para avaliação
        T("CONTRATADO", "contrato", frozenset({"ADJUDICADO"})),
    ),
))
# RFQ: cotação simples, sem avaliação técnica nem shortlist (§15: não usar o fluxo pesado de RFP).
COTACAO_EMPRESA = workflow.registrar(workflow.Workflow(
    codigo="ENTERPRISE_RFQ_BUY@1", lado=tipos.Lado.COMPRA, inicial="RASCUNHO",
    estados=("RASCUNHO", "PUBLICADO", "RECEBENDO_PROPOSTAS", "EM_NEGOCIACAO", "EM_APROVACAO", "ADJUDICADO", "CONTRATADO",
             "CANCELADO"),
    finais=("CONTRATADO", "CANCELADO"), mensagens=_MENSAGENS_EMPRESA,
    transicoes=(
        T("PUBLICADO", "status", frozenset({"RASCUNHO"})),
        T("RECEBENDO_PROPOSTAS", "status", frozenset({"PUBLICADO", "EM_NEGOCIACAO"})),
        T("EM_NEGOCIACAO", "status", frozenset({"RECEBENDO_PROPOSTAS"})),
        T("CANCELADO", "status", frozenset({"RASCUNHO", "PUBLICADO", "RECEBENDO_PROPOSTAS", "EM_NEGOCIACAO", "EM_APROVACAO"})),
        T("EM_APROVACAO", "aprovacao", frozenset({"RECEBENDO_PROPOSTAS", "EM_NEGOCIACAO"})),
        T("ADJUDICADO", "aprovacao", frozenset({"EM_APROVACAO"})),
        T("RECEBENDO_PROPOSTAS", "aprovacao", frozenset({"EM_APROVACAO"})),
        T("CONTRATADO", "contrato", frozenset({"ADJUDICADO"})),
    ),
))
# RFI, EOI e qualificação de fornecedor: coleta e avaliação, sem adjudicação nem contrato.
CONSULTA_EMPRESA = workflow.registrar(workflow.Workflow(
    codigo="ENTERPRISE_RFI_BUY@1", lado=tipos.Lado.COMPRA, inicial="RASCUNHO",
    estados=("RASCUNHO", "PUBLICADO", "RECEBENDO_RESPOSTAS", "EM_AVALIACAO", "ENCERRADO", "CANCELADO"),
    finais=("ENCERRADO", "CANCELADO"),
    transicoes=(
        T("PUBLICADO", "status", frozenset({"RASCUNHO"})),
        T("RECEBENDO_RESPOSTAS", "status", frozenset({"PUBLICADO"})),
        T("EM_AVALIACAO", "status", frozenset({"RECEBENDO_RESPOSTAS"})),
        T("ENCERRADO", "status", frozenset({"EM_AVALIACAO"})),
        T("CANCELADO", "status", frozenset({"RASCUNHO", "PUBLICADO", "RECEBENDO_RESPOSTAS", "EM_AVALIACAO"})),
    ),
))
POLITICA_EMPRESA = ruleset.registrar(ruleset.Ruleset(
    codigo="ENTERPRISE_SOURCING_POLICY@1",
    descricao="Compra privada: sem regime legal de contratação pública; valem a política e as alçadas do próprio cliente.",
    fonte="Política de compras do próprio cliente (não é norma legal)",
))
TIPOS_EMPRESA = ("RFP", "RFI", "RFQ", "EOI", "PRIVATE_TENDER", "VENDOR_QUALIFICATION", "STRATEGIC_SOURCING_EVENT")
workflow.vincular(LADO, tipos.Segmento.EMPRESA, SOURCING_EMPRESA, POLITICA_EMPRESA)  # RFP, PRIVATE_TENDER, evento estratégico
workflow.vincular(LADO, tipos.Segmento.EMPRESA, COTACAO_EMPRESA, POLITICA_EMPRESA, tipos_processo=("RFQ",))
workflow.vincular(LADO, tipos.Segmento.EMPRESA, CONSULTA_EMPRESA, POLITICA_EMPRESA, tipos_processo=("RFI", "EOI", "VENDOR_QUALIFICATION"))


def configuracao_empresa(tipo_processo: str) -> tuple[workflow.Workflow, ruleset.Ruleset | None]:
    return workflow.resolver(LADO, tipos.Segmento.EMPRESA, tipo_processo)
