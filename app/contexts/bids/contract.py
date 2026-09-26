"""Contrato público do contexto Bid Intelligence (Fase 9)."""

from app.contexts.bids import analise, cofre, concorrencia, conformidade, contratos, documentos, go_no_go, grafo, licitacoes, prazos, repositorio, tipos, workspace
from app.contexts.bids.fontes import registro as fontes
from app.contexts.bids.fontes.pncp import FontePncp

__all__ = [
    "FontePncp", "analise", "cofre", "concorrencia", "conformidade", "contratos", "documentos", "fontes", "go_no_go", "grafo",
    "licitacoes", "prazos", "repositorio", "tipos", "workspace",
]

# Fase 12: registra as ferramentas deste contexto no B2B ON Intelligence Agent.
from app.contexts.bids import ferramentas as _ferramentas  # noqa: E402, F401
