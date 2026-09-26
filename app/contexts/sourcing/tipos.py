"""Vocabulário do núcleo de sourcing (D-055, `18_STRATEGIC_SOURCING.md` §3)."""

from enum import StrEnum


class Lado(StrEnum):
    VENDA = "SELL"
    COMPRA = "BUY"


class Segmento(StrEnum):
    PUBLICO = "PUBLIC"
    EMPRESA = "ENTERPRISE"


TIPOS_PROCESSO = (
    "PUBLIC_TENDER", "RFP", "RFI", "RFQ", "EOI", "DIRECT_AWARD", "PRICE_REGISTRATION", "FRAMEWORK_AGREEMENT",
    "PRIVATE_TENDER", "STRATEGIC_SOURCING_EVENT", "VENDOR_QUALIFICATION",
)

# Resultado de avaliação de requisito: falta de dado é UNKNOWN, nunca "não atende".
STATUS_CONFORMIDADE = ("COMPLIANT", "PARTIALLY_COMPLIANT", "NON_COMPLIANT", "UNKNOWN", "REQUIRES_REVIEW")
