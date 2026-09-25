"""Modelo canônico da Business Network (Fase 7, §27-§29).

Diferente do comercial e do procurement, estes objetos atravessam
tenants por natureza: por isso cada um diz sua visibilidade, e a
classificação nunca passa de PUBLIC/INTERNAL.
"""

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from app.contexts.shared.canonical.base import DataOrigin


class BusinessRelationType(StrEnum):
    SUPPLIER_OF = "SUPPLIER_OF"
    CUSTOMER_OF = "CUSTOMER_OF"
    PARTNER_OF = "PARTNER_OF"
    RESELLER_OF = "RESELLER_OF"
    DISTRIBUTOR_OF = "DISTRIBUTOR_OF"
    INTEGRATES_WITH = "INTEGRATES_WITH"
    USES_TECHNOLOGY = "USES_TECHNOLOGY"
    PROVIDES_SERVICE = "PROVIDES_SERVICE"
    PROVIDES_PRODUCT = "PROVIDES_PRODUCT"
    INTERESTED_IN = "INTERESTED_IN"
    LOOKING_FOR = "LOOKING_FOR"
    CONNECTED_TO = "CONNECTED_TO"
    INVESTS_IN = "INVESTS_IN"  # legado (Fase 1D), fora do §28


class EdgeVisibility(StrEnum):
    PUBLIC = "publica"
    CONNECTIONS = "conexoes"
    PRIVATE = "privada"


class EdgeVerification(StrEnum):
    SELF_DECLARED = "autodeclarada"
    CONFIRMED_BY_COUNTERPARTY = "confirmada_pela_contraparte"
    PLATFORM_CONNECTION = "conexao_aceita"


class EdgeConfidence(StrEnum):
    HIGH = "ALTA"
    MEDIUM = "MEDIA"
    LOW = "BAIXA"


class CompanyStatus(StrEnum):
    UNCLAIMED = "NAO_REIVINDICADA"
    CLAIMED = "REIVINDICADA"
    VERIFIED = "VERIFICADA"
    MERGED = "MESCLADA"


class CompanyIdentity(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    tenant_id: str | None
    cnpj: str | None
    display_name: str
    status: CompanyStatus
    origin: DataOrigin


class BusinessEdge(BaseModel):
    """§28: source, visibility, confidence, verification, validity, creator, metadata."""

    model_config = ConfigDict(frozen=True)

    id: str
    type: BusinessRelationType
    from_company: CompanyIdentity
    to_company: CompanyIdentity
    source: str
    visibility: EdgeVisibility
    confidence: EdgeConfidence
    verification: EdgeVerification
    valid_from: date | None = None
    valid_until: date | None = None
    creator_tenant_id: str | None = None
    metadata: dict = {}
