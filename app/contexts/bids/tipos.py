"""Vocabulário do Bid Intelligence (§31-§36)."""

from app.contexts.bids import fluxo
from app.contexts.sourcing import contract as sourcing

MODALIDADES = (
    "PUBLIC_TENDER", "RFP", "RFI", "RFQ", "EOI", "DIRECT_AWARD",
    "PRICE_REGISTRATION", "FRAMEWORK_AGREEMENT", "PRIVATE_RFP",
    # Enterprise Bids (Phase C): processo privado recebido pelo fornecedor; o prefixo marca o segmento
    "PRIVATE_RFI", "PRIVATE_RFQ", "PRIVATE_TENDER",
)
# Estados vêm do workflow declarativo (S4): `fluxo.py` é a fonte única.
STATUS_LICITACAO = fluxo.LICITACAO_PUBLICA.estados
STATUS_FINAIS = fluxo.LICITACAO_PUBLICA.finais
TIPOS_DOCUMENTO = ("EDITAL", "TR", "ANEXO", "ESCLARECIMENTO", "ATA", "CONTRATO", "OUTRO")

# §33 (edital) + §34 (TR)
CATEGORIAS_REQUISITO = (
    "OBJETO", "HABILITACAO", "QUALIFICACAO_TECNICA", "CERTIFICACAO", "SLA", "PRAZO", "GARANTIA",
    "PENALIDADE", "CRITERIO", "LOTE", "ITEM", "OBRIGACAO", "RISCO",
    "REQUISITO_TECNICO", "REQUISITO_COMERCIAL", "REQUISITO_LEGAL",
    "PERGUNTA",  # pergunta de RFI/questionário a responder (Phase C)
)
# Categorias que exigem comprovação documental (cofre) para COMPLIANT.
CATEGORIAS_DOCUMENTAIS = ("HABILITACAO", "QUALIFICACAO_TECNICA", "CERTIFICACAO", "REQUISITO_LEGAL")
# Categorias que viram linha da matriz de conformidade.
CATEGORIAS_MATRIZ = CATEGORIAS_DOCUMENTAIS + ("REQUISITO_TECNICO", "REQUISITO_COMERCIAL", "SLA", "GARANTIA", "OBRIGACAO")

# Vocabulário único do Evaluation Engine compartilhado (S1).
STATUS_CONFORMIDADE = sourcing.tipos.STATUS_CONFORMIDADE

TIPOS_COFRE = (
    "CERTIDAO", "CONTRATO_SOCIAL", "PROCURACAO", "BALANCO", "CERTIFICACAO", "ATESTADO", "CURRICULO",
    "ISO", "CARTA_FABRICANTE", "PARCERIA", "DECLARACAO", "JURIDICO", "OUTRO",
)
