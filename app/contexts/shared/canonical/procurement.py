"""Procurement Canonical Model — fundação (Master Prompt §12 — PROCUREMENT DOMAIN).

Só o modelo. Não há tabelas nem fluxos de Procurement nesta fase (Fases
9 e 10). Regras que já valem aqui:

- Regimes jurídicos variam (§37): nada de enum fechado para modalidade ou
  status. `modality`/`status` são strings parametrizáveis, com o valor
  original preservado.
- Classificação default **CONFIDENTIAL** para o que é interno do órgão
  comprador (demanda, plano, orçamento, avaliação). Só entidades cuja
  fonte é pública (edital publicado, contrato publicado) devem ser
  marcadas PUBLIC pelo adapter. É a base da barreira Buy/Sell (§50).
- Toda extração documental carrega `EvidenceRef` (§33, §48).
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.contexts.shared.canonical.base import CanonicalEntity, DataClassification
from app.contexts.shared.canonical.commercial import Money


class EvidenceRef(BaseModel):
    """Proveniência de um fato extraído de documento (§33): fonte,
    documento, página, cláusula e o trecho literal."""

    model_config = ConfigDict(frozen=True)

    source: str
    document_id: str | None = None
    page: int | None = None
    clause: str | None = None
    excerpt: str | None = None


class _Confidential(CanonicalEntity):
    classification: DataClassification = DataClassification.CONFIDENTIAL


class PublicOrganization(CanonicalEntity):
    name: str
    tax_id: str | None = None
    sphere: str | None = None  # federal | estadual | municipal | estatal | privada_regulada
    legal_regime: str | None = None  # ex.: "Lei 14.133/2021"; parametrizável


class ProcurementUnit(CanonicalEntity):
    public_organization_id: str
    name: str
    code: str | None = None


class ProcurementUser(_Confidential):
    procurement_unit_id: str
    full_name: str
    role: str | None = None


class Demand(_Confidential):
    requesting_unit_id: str
    requester_id: str | None = None
    business_need: str
    justification: str | None = None
    category: str | None = None
    estimated_value: Money | None = None
    priority: str | None = None
    required_date: date | None = None
    budget_reference: str | None = None
    related_plan_id: str | None = None
    status: str


class ProcurementPlan(_Confidential):
    public_organization_id: str
    year: int
    name: str
    status: str
    planned_value: Money | None = None


class PCAItem(_Confidential):
    plan_id: str
    description: str
    category: str | None = None
    estimated_value: Money | None = None
    expected_quarter: str | None = None
    demand_ids: list[str] = []
    status: str


class ProcurementProcess(_Confidential):
    public_organization_id: str
    procurement_unit_id: str | None = None
    pca_item_id: str | None = None
    number: str | None = None
    object: str
    modality: str | None = None
    status: str
    estimated_value: Money | None = None
    opened_at: datetime | None = None


class ProcurementDocument(_Confidential):
    process_id: str | None = None
    kind: str  # ETP | TR | EDITAL | CONTRATO | ADITIVO | ATA | PESQUISA_PRECO | PARECER | OUTRO
    title: str
    url: str | None = None
    published_at: datetime | None = None


class ProcurementLot(CanonicalEntity):
    process_id: str
    number: str
    description: str | None = None


class ProcurementItem(CanonicalEntity):
    process_id: str
    lot_id: str | None = None
    description: str
    quantity: float | None = None
    unit: str | None = None
    estimated_unit_price: Money | None = None


class Supplier(CanonicalEntity):
    legal_name: str
    tax_id: str | None = None
    categories: list[str] = []


class SupplierPerformance(_Confidential):
    supplier_id: str
    contract_id: str | None = None
    metric: str
    value: float | None = None
    evidence: list[EvidenceRef] = []


class PriceResearch(_Confidential):
    process_id: str | None = None
    item_description: str
    unit_price: Money
    source_description: str
    collected_at: datetime | None = None


class BudgetAllocation(_Confidential):
    public_organization_id: str
    reference: str
    amount: Money
    fiscal_year: int | None = None


class PublicContract(CanonicalEntity):
    public_organization_id: str
    supplier_id: str
    process_id: str | None = None
    number: str | None = None
    object: str
    value: Money | None = None
    starts_at: date | None = None
    ends_at: date | None = None
    status: str


class Deliverable(_Confidential):
    contract_id: str
    description: str
    due_at: date | None = None
    delivered_at: date | None = None
    status: str


class Inspection(_Confidential):
    contract_id: str
    deliverable_id: str | None = None
    performed_at: date | None = None
    result: str | None = None
    notes: str | None = None


class Amendment(CanonicalEntity):
    contract_id: str
    number: str | None = None
    kind: str | None = None  # prazo | valor | escopo
    value_delta: Money | None = None
    new_end_date: date | None = None


class ProcurementRisk(_Confidential):
    """Sinal analítico (§46): nunca conclusão jurídica. `label` usa
    linguagem como "requires review" / "potential inconsistency"."""

    subject_type: str
    subject_id: str
    signal: str
    label: str
    evidence: list[EvidenceRef] = []


class BidOpportunity(CanonicalEntity):
    """Oportunidade de licitação/RFP vista pelo lado vendedor (§32)."""

    issuer_name: str
    issuer_id: str | None = None
    account_id: str | None = None
    kind: str  # PUBLIC_TENDER | RFP | RFI | RFQ | EOI | DIRECT_AWARD | PRICE_REGISTRATION | FRAMEWORK_AGREEMENT | PRIVATE_RFP
    object: str
    modality: str | None = None
    publication_date: date | None = None
    submission_deadline: datetime | None = None
    estimated_value: Money | None = None
    status: str


PROCUREMENT_ENTITIES: tuple[type[CanonicalEntity], ...] = (
    PublicOrganization, ProcurementUnit, ProcurementUser, Demand, ProcurementPlan, PCAItem,
    ProcurementProcess, ProcurementDocument, ProcurementLot, ProcurementItem, Supplier,
    SupplierPerformance, PriceResearch, BudgetAllocation, PublicContract, Deliverable,
    Inspection, Amendment, ProcurementRisk, BidOpportunity,
)
