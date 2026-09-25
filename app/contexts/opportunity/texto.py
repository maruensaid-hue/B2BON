"""Casamento de texto do Opportunity Intelligence: reexporta o Shared Kernel
(`app/contexts/shared/texto.py`), para onde foi movido na Fase 9."""

from app.contexts.shared.texto import contem_literal, normalizar, termos, termos_em_comum

__all__ = ["contem_literal", "normalizar", "termos", "termos_em_comum"]
