"""Commercial Canonical Model (Master Prompt §12 — COMMERCIAL DOMAIN).

Regras de modelagem:
- Organization (identidade da empresa) ≠ Account (relação comercial do
  tenant com ela) ≠ Customer (Account que virou cliente, com datas de
  receita/churn). Não fundimos entidades diferentes só para reaproveitar
  código (§12, última linha).
- Valores monetários são `Money` (Decimal + moeda), nunca float solto.
- Campo desconhecido fica `None`. Nenhum adapter inventa valor.
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from app.contexts.shared.canonical.base import CanonicalEntity


class Money(BaseModel):
    model_config = ConfigDict(frozen=True)

    amount: Decimal
    currency: str = "BRL"


# --- Enums -------------------------------------------------------------------


class AccountLifecycle(StrEnum):
    PROSPECT = "PROSPECT"
    LEAD = "LEAD"
    QUALIFIED = "QUALIFIED"
    CUSTOMER = "CUSTOMER"
    CHURNED = "CHURNED"
    DISQUALIFIED = "DISQUALIFIED"


class StageType(StrEnum):
    OPEN = "OPEN"
    WON = "WON"
    LOST = "LOST"


class OpportunityStatus(StrEnum):
    OPEN = "OPEN"
    WON = "WON"
    LOST = "LOST"


class ActivityKind(StrEnum):
    CALL = "CALL"
    EMAIL = "EMAIL"
    MEETING = "MEETING"
    NOTE = "NOTE"
    TASK = "TASK"
    STAGE_CHANGE = "STAGE_CHANGE"
    OTHER = "OTHER"


class Channel(StrEnum):
    EMAIL = "EMAIL"
    WHATSAPP = "WHATSAPP"
    LINKEDIN = "LINKEDIN"
    SMS = "SMS"
    PHONE = "PHONE"
    OTHER = "OTHER"


class MessageStatus(StrEnum):
    """Ciclo de vida de comunicação (§17). Aprovação humana é obrigatória
    antes de SCHEDULED/SENT para conteúdo gerado por IA."""

    DRAFT = "DRAFT"
    AI_GENERATED = "AI_GENERATED"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EDITED = "EDITED"
    SCHEDULED = "SCHEDULED"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class MeetingStatus(StrEnum):
    PROPOSED = "PROPOSED"
    SCHEDULED = "SCHEDULED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    NO_SHOW = "NO_SHOW"
    RESCHEDULED = "RESCHEDULED"


class BuyingRole(StrEnum):
    ECONOMIC_BUYER = "ECONOMIC_BUYER"
    TECHNICAL_BUYER = "TECHNICAL_BUYER"
    USER_BUYER = "USER_BUYER"
    CHAMPION = "CHAMPION"
    INFLUENCER = "INFLUENCER"
    BLOCKER = "BLOCKER"
    UNKNOWN = "UNKNOWN"


# --- Identidade ----------------------------------------------------------------


class Organization(CanonicalEntity):
    legal_name: str
    trade_name: str | None = None
    tax_id: str | None = Field(default=None, description="CNPJ (14 dígitos) ou equivalente.")
    domain: str | None = None
    industry: str | None = None
    size: str | None = None
    region: str | None = None


class Person(CanonicalEntity):
    organization_id: str | None = None
    full_name: str
    job_title: str | None = None
    email: str | None = None
    phone: str | None = None
    linkedin_url: str | None = None
    suppressed_at: datetime | None = Field(default=None, description="Opt-out/LGPD: não contatar.")


# --- Relação comercial -----------------------------------------------------------


class Account(CanonicalEntity):
    organization_id: str
    owner_user_id: str | None = None
    lifecycle: AccountLifecycle
    fit_score: float | None = None
    next_step: str | None = None
    next_step_at: datetime | None = None


class Contact(CanonicalEntity):
    account_id: str
    person_id: str
    buying_role: BuyingRole = BuyingRole.UNKNOWN
    buying_role_confirmed: bool = False
    last_interaction_at: datetime | None = None


class Lead(CanonicalEntity):
    """Registro de prospecção ainda não qualificado (conceito Salesforce
    Lead / RD Station lead). Pode existir sem Organization resolvida."""

    organization_id: str | None = None
    person_id: str | None = None
    company_name: str | None = None
    status: AccountLifecycle = AccountLifecycle.LEAD
    source_channel: str | None = None


class Customer(CanonicalEntity):
    account_id: str
    customer_since: datetime
    churned_at: datetime | None = None


# --- Pipeline ----------------------------------------------------------------------


class Pipeline(CanonicalEntity):
    name: str


class PipelineStage(CanonicalEntity):
    pipeline_id: str
    name: str
    order: int
    stage_type: StageType


class Opportunity(CanonicalEntity):
    account_id: str
    primary_contact_id: str | None = None
    owner_user_id: str | None = None
    pipeline_id: str
    stage_id: str
    name: str
    amount: Money | None = None
    probability: int | None = Field(default=None, ge=0, le=100)
    status: OpportunityStatus
    offer_id: str | None = None
    closed_at: datetime | None = None
    lost_reason: str | None = None


class Activity(CanonicalEntity):
    account_id: str | None = None
    opportunity_id: str | None = None
    user_id: str | None = None
    kind: ActivityKind
    source_type: str = Field(description="Tipo original no sistema de origem (preservado).")
    description: str


class Meeting(CanonicalEntity):
    account_id: str
    contact_id: str | None = None
    owner_user_id: str | None = None
    scheduled_at: datetime | None = None
    status: MeetingStatus
    qualified: bool | None = None
    summary: str | None = None
    summary_origin: str | None = Field(default=None, description="DataOrigin do resumo (AI_INFERENCE quando gerado por IA).")


class Message(CanonicalEntity):
    contact_id: str
    channel: Channel
    subject: str | None = None
    body: str
    status: MessageStatus
    scheduled_for: datetime | None = None
    sent_at: datetime | None = None
    opened_at: datetime | None = None
    bounced_at: datetime | None = None


class Interaction(CanonicalEntity):
    """Sinal de relacionamento registrado (contato, reclamação, elogio…),
    matéria-prima do churn do MAP."""

    account_id: str
    kind: str
    description: str | None = None


class CSMetric(CanonicalEntity):
    account_id: str
    metric: str = Field(description="Ex.: 'NPS'.")
    value: float | None = None
    scale_max: float | None = None
    collected_at: datetime | None = None


# --- Oferta, proposta, contrato, receita -------------------------------------------


class Product(CanonicalEntity):
    name: str
    category: str | None = None
    description: str | None = None
    active: bool = True


class Offer(CanonicalEntity):
    """Offer Intelligence (§25). Campos opcionais: o que o tenant não
    cadastrou fica vazio — nunca preenchido por IA sem marcação."""

    name: str
    category: str | None = None
    description: str | None = None
    problems_solved: list[str] = []
    pain_points: list[str] = []
    use_cases: list[str] = []
    icps: list[str] = []
    personas: list[str] = []
    industries: list[str] = []
    requirements: list[str] = []
    prerequisites: list[str] = []
    incompatibilities: list[str] = []
    differentiators: list[str] = []
    objections: list[str] = []
    proof_points: list[str] = []
    cases: list[str] = []
    cross_sell: list[str] = []
    upsell: list[str] = []
    bundles: list[str] = []
    pricing_model: str | None = None
    price_min: Money | None = None
    price_max: Money | None = None
    average_ticket: Money | None = None
    average_margin: float | None = None
    sales_playbook: str | None = None
    discovery_questions: list[str] = []
    qualification_criteria: list[str] = []
    active: bool = True


class Proposal(CanonicalEntity):
    opportunity_id: str
    version: int
    name: str | None = None
    file_name: str | None = None
    generated_automatically: bool = False


class Contract(CanonicalEntity):
    account_id: str
    opportunity_id: str | None = None
    value: Money | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    status: str | None = None


class Revenue(CanonicalEntity):
    account_id: str
    opportunity_id: str | None = None
    amount: Money
    recognized_at: datetime | None = None
    kind: str = Field(default="WON_DEAL", description="WON_DEAL | RECURRING | ONE_OFF")


class Invoice(CanonicalEntity):
    account_id: str
    number: str | None = None
    amount: Money
    issued_at: datetime | None = None
    due_at: datetime | None = None
    paid_at: datetime | None = None
    status: str | None = None


class BusinessIntent(CanonicalEntity):
    """Necessidade publicada por uma empresa (Intent da Rede)."""

    category: str
    title: str
    description: str
    requirements: list[str] = []
    budget_range: str | None = None
    location: str | None = None
    deadline: datetime | None = None
    desired_supplier_profile: str | None = None
    visibility: str
    status: str
    expires_at: datetime | None = None


COMMERCIAL_ENTITIES: tuple[type[CanonicalEntity], ...] = (
    Organization, Person, Lead, Account, Contact, Opportunity, Pipeline, PipelineStage,
    Activity, Meeting, Message, Product, Offer, Proposal, Contract, Customer, Revenue,
    Invoice, Interaction, CSMetric, BusinessIntent,
)
