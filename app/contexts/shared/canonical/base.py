"""Base do modelo canônico: identidade, proveniência e classificação.

Todo objeto canônico carrega três coisas que o ORM atual não tem de
forma uniforme:

- `source`: de qual sistema veio e com qual id lá (proveniência, §63).
- `origin`: natureza do dado — OFFICIAL / INTERNAL / SELF_DECLARED /
  AI_INFERENCE (§42). "Dado inferido por IA" nunca é apresentado como fato.
- `classification`: PUBLIC / INTERNAL / CONFIDENTIAL / RESTRICTED. É o
  eixo que a barreira Buy/Sell (§50, Fase 10) e a Business Network
  (§51) usam para decidir o que pode atravessar tenants. Default
  INTERNAL: nada é público por acidente.
"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class DataClassification(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


class DataOrigin(StrEnum):
    OFFICIAL = "OFFICIAL"
    INTERNAL = "INTERNAL"
    SELF_DECLARED = "SELF_DECLARED"
    AI_INFERENCE = "AI_INFERENCE"


class SourceRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    system: str = Field(description="Sistema de origem, ex.: 'b2bon_crm', 'hubspot', 'pncp'.")
    external_id: str = Field(description="Identificador no sistema de origem.")
    entity: str = Field(description="Nome da entidade no sistema de origem, ex.: 'conta', 'deal'.")
    fetched_at: datetime | None = None
    url: str | None = None


def canonical_id(system: str, entity: str, external_id: str | int) -> str:
    """Id canônico estável e legível: `<sistema>:<entidade>:<id>`. Dois
    adapters diferentes nunca colidem, e o mesmo registro sincronizado
    duas vezes gera o mesmo id (base da idempotência da Fase 3)."""
    return f"{system}:{entity}:{external_id}"


class CanonicalEntity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    tenant_id: str
    source: SourceRef
    origin: DataOrigin = DataOrigin.INTERNAL
    classification: DataClassification = DataClassification.INTERNAL
    created_at: datetime | None = None
    updated_at: datetime | None = None
