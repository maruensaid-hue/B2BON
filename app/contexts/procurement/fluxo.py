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
    descricao="Contratação pública brasileira (Lei 14.133/2021).",
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
