"""Contrato público do contexto de enriquecimento governado (créditos de enriquecimento, pesquisa de decisores).

Separado do FinOps de IA: nenhuma carteira, lote ou movimento é compartilhado entre as duas categorias."""

from app.contexts.enriquecimento import config, execucao, ledger, painel, pesquisa
from app.contexts.enriquecimento.pesquisa import Solicitante

__all__ = ["Solicitante", "config", "execucao", "ledger", "painel", "pesquisa"]
