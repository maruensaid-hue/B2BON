"""Workflow e ruleset do lado vendedor (S4, D-055).

Fonte única dos estados de uma licitação. Reproduz o comportamento anterior
à S4 (sem restrição de origem):
- IDENTIFICADA, EM_ANALISE, PROPOSTA_ENVIADA e CANCELADA: mudança de status;
- GO e NO_GO: só pela decisão Go/No-Go (recomendação + justificativa);
- GANHA e PERDIDA: só pelo registro de resultado (vencedor e valor).

`ENTERPRISE_RFP_SELL@1` foi o mesmo fluxo aplicado ao RFP privado (S4). A
Phase C criou a v2 para todo processo privado recebido pelo fornecedor
(RFP, RFI, RFQ, concorrência privada): igual à v1 mais a **negociação**
(`EM_NEGOCIACAO`), que só vem depois da proposta enviada. A v1 continua
registrada (histórico). `PRIVATE_RFP@1` não tem regra regulatória: é
contratação privada.

Classificação única da modalidade em (segmento, tipo de processo), usada
pelo espelho e pela resolução do workflow: a regra "RFP privado é
Enterprise" vive só aqui.
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
_fluxo("ENTERPRISE_RFP_SELL@1")  # histórico (S3/S4); vínculo atual é a v2
PROCESSO_PRIVADO = workflow.registrar(workflow.Workflow(
    codigo="ENTERPRISE_RFP_SELL@2", lado=tipos.Lado.VENDA,
    estados=(*ESTADOS[:5], "EM_NEGOCIACAO", *ESTADOS[5:]), inicial="IDENTIFICADA",
    finais=("NO_GO", "GANHA", "PERDIDA", "CANCELADA"), mensagens=_MENSAGENS,
    transicoes=(*_TRANSICOES, T("EM_NEGOCIACAO", "status", frozenset({"PROPOSTA_ENVIADA"}))),
))
REGRAS_RFP_PRIVADO = ruleset.registrar(ruleset.Ruleset(
    codigo="PRIVATE_RFP@1", descricao="RFP privado: sem regime legal de contratação pública.",
    fonte="Regras do próprio comprador privado (edital/RFP do emissor)",
))
LADO = tipos.Lado.VENDA
workflow.vincular(LADO, tipos.Segmento.PUBLICO, LICITACAO_PUBLICA)
workflow.vincular(LADO, tipos.Segmento.EMPRESA, PROCESSO_PRIVADO, REGRAS_RFP_PRIVADO)
# modalidade privada → tipo de processo universal (o prefixo PRIVATE_ marca o segmento Enterprise)
PRIVADAS = {"PRIVATE_RFP": "RFP", "PRIVATE_RFI": "RFI", "PRIVATE_RFQ": "RFQ", "PRIVATE_TENDER": "PRIVATE_TENDER"}


def classificar(modalidade: str | None) -> tuple[tipos.Segmento, str]:
    """Modalidade da licitação → (segmento, tipo de processo)."""
    if modalidade in PRIVADAS:
        return tipos.Segmento.EMPRESA, PRIVADAS[modalidade]
    return tipos.Segmento.PUBLICO, modalidade if modalidade in tipos.TIPOS_PROCESSO else "PUBLIC_TENDER"


def configuracao(modalidade: str | None) -> tuple[workflow.Workflow, ruleset.Ruleset | None]:
    return workflow.resolver(LADO, *classificar(modalidade))


def de(modalidade: str | None) -> workflow.Workflow:
    return configuracao(modalidade)[0]
