"""Contrato público do contexto Public Procurement (Fase 10).

Só a API do próprio lado comprador (`app/api/v1/procurement.py`) usa este
contrato. Sell Side, Business Network, CRM, PREDATOR, MAP, Opportunity e
Intelligence não o importam (barreira Buy/Sell, fitness function).
"""

from app.contexts.procurement import cadastros, contratos, demandas, documentos, fornecedores, nba, planejamento, precos, riscos, tipos, workspace

__all__ = [
    "cadastros", "contratos", "demandas", "documentos", "fornecedores", "nba", "planejamento", "precos", "riscos", "tipos",
    "workspace",
]
