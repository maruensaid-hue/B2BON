"""Canonical Business Model (Fase 2, Master Prompt §12).

Modelo independente de CRM/fornecedor. Adapters (B2B ON CRM, e na Fase 13
Salesforce/HubSpot/Pipedrive/RD Station) traduzem de/para ele; os
contextos consumidores (MAP, PREDATOR, Intelligence) passam a poder
operar sobre ele sem saber de onde o dado veio.
"""

from app.contexts.shared.canonical.base import (
    CanonicalEntity,
    DataClassification,
    DataOrigin,
    SourceRef,
    canonical_id,
)

__all__ = ["CanonicalEntity", "DataClassification", "DataOrigin", "SourceRef", "canonical_id"]
