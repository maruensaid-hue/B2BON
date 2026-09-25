"""Contrato público do contexto Opportunity Intelligence (Fase 6)."""

from app.contexts.opportunity import necessidades
from app.contexts.opportunity.card import montar as card_oportunidade
from app.contexts.opportunity.card import white_space_da_conta
from app.contexts.opportunity.explicavel import INSUFFICIENT_INFORMATION, METODOLOGIA

__all__ = ["INSUFFICIENT_INFORMATION", "METODOLOGIA", "card_oportunidade", "necessidades", "white_space_da_conta"]
