"""Workflow e ruleset do lado vendedor (S4, D-055).

Fonte única dos estados de uma licitação. Reproduz o comportamento anterior
à S4 (sem restrição de origem):
- IDENTIFICADA, EM_ANALISE, PROPOSTA_ENVIADA e CANCELADA: mudança de status;
- GO e NO_GO: só pela decisão Go/No-Go (recomendação + justificativa);
- GANHA e PERDIDA: só pelo registro de resultado (vencedor e valor).

`ENTERPRISE_RFP_SELL@1` é o mesmo fluxo aplicado ao RFP privado, com código
próprio para que o fluxo enterprise (S7) nasça como nova versão sem
reescrever o histórico. `PRIVATE_RFP@1` não tem regra regulatória: é
contratação privada.
"""

from app.contexts.sourcing.contract import ruleset, tipos, workflow

T = workflow.Transicao
ESTADOS = ("IDENTIFICADA", "EM_ANALISE", "GO", "NO_GO", "PROPOSTA_ENVIADA", "GANHA", "PERDIDA", "CANCELADA")
_TRANSICOES = (
    T("IDENTIFICADA", "status"), T("EM_ANALISE", "status"), T("PROPOSTA_ENVIADA", "status"), T("CANCELADA", "status"),
    T("GO", "go_no_go"), T("NO_GO", "go_no_go"),
    T("GANHA", "resultado"), T("PERDIDA", "resultado"),
)
_MENSAGENS = {
    "go_no_go": "GO/NO_GO é registrado pela decisão Go/No-Go, com a recomendação e a justificativa.",
    "resultado": "Use o registro de resultado para informar vencedor e valor.",
}


def _fluxo(codigo: str) -> workflow.Workflow:
    return workflow.registrar(workflow.Workflow(
        codigo=codigo, lado=tipos.Lado.VENDA, estados=ESTADOS, inicial="IDENTIFICADA",
        finais=("NO_GO", "GANHA", "PERDIDA", "CANCELADA"), transicoes=_TRANSICOES, mensagens=_MENSAGENS,
    ))


LICITACAO_PUBLICA = _fluxo("PUBLIC_TENDER_SELL@1")
RFP_PRIVADO = _fluxo("ENTERPRISE_RFP_SELL@1")
REGRAS_RFP_PRIVADO = ruleset.registrar(ruleset.Ruleset(
    codigo="PRIVATE_RFP@1", descricao="RFP privado: sem regime legal de contratação pública; regras do próprio comprador.",
))


def empresa(modalidade: str | None) -> bool:
    return modalidade == "PRIVATE_RFP"


def de(modalidade: str | None) -> workflow.Workflow:
    return RFP_PRIVADO if empresa(modalidade) else LICITACAO_PUBLICA


def regras_de(modalidade: str | None) -> ruleset.Ruleset | None:
    return REGRAS_RFP_PRIVADO if empresa(modalidade) else None
