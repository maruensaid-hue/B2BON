# 04 — CANONICAL BUSINESS MODEL (Fase 2)

Código: `app/contexts/shared/canonical/` (`base.py`, `commercial.py`,
`procurement.py`). JSON Schema de qualquer entidade:
`Entidade.model_json_schema()`.

## 1. Princípios

| Princípio | Como está no código |
|---|---|
| Independente de fornecedor | Nenhum nome de campo vem de um CRM específico; valores originais ficam em `source` / `source_type` |
| Proveniência obrigatória (§63) | `CanonicalEntity.source: SourceRef(system, external_id, entity, fetched_at, url)` |
| Natureza do dado (§42) | `origin: OFFICIAL / INTERNAL / SELF_DECLARED / AI_INFERENCE` |
| Classificação (§50, §61) | `classification: PUBLIC / INTERNAL / CONFIDENTIAL / RESTRICTED`, default INTERNAL; entidades internas do comprador default CONFIDENTIAL |
| Não inventar (§23) | Campo desconhecido = `None`/lista vazia; `extra="forbid"` rejeita campo não modelado |
| Imutável | `frozen=True`: um consumidor não altera o objeto por acidente |
| Dinheiro | `Money(amount: Decimal, currency="BRL")`, nunca float |
| Id estável | `canonical_id(system, entity, external_id)` → `b2bon_crm:account:42` |
| Não fundir entidades diferentes (§12) | Organization ≠ Account ≠ Customer; Person ≠ Contact |

## 2. Domínio comercial (21 entidades)

Organization, Person, Lead, Account, Contact, Opportunity, Pipeline,
PipelineStage, Activity, Meeting, Message, Product, Offer, Proposal,
Contract, Customer, Revenue, Invoice, Interaction, CSMetric, BusinessIntent.

Enums: `AccountLifecycle`, `StageType`, `OpportunityStatus`,
`ActivityKind`, `Channel`, `MessageStatus` (os 11 estados do §17),
`MeetingStatus`, `BuyingRole`.

`Offer` contém todos os campos de Offer Intelligence do §25 (Fase 6 usa).

## 3. Domínio de procurement (20 entidades, só fundação)

PublicOrganization, ProcurementUnit, ProcurementUser, Demand,
ProcurementPlan, PCAItem, ProcurementProcess, ProcurementDocument,
ProcurementLot, ProcurementItem, Supplier, SupplierPerformance,
PriceResearch, BudgetAllocation, PublicContract, Deliverable,
Inspection, Amendment, ProcurementRisk, BidOpportunity.

- Modalidade e status são strings parametrizáveis. Regimes jurídicos
  variam (§37), então não há enum fechado.
- `EvidenceRef(source, document_id, page, clause, excerpt)` para toda
  extração documental (§33, §48).
- `ProcurementRisk.label` usa linguagem de sinal analítico, nunca
  conclusão jurídica (§46).
- **Não há tabelas de procurement nesta fase** (Fases 9/10).

## 4. Validação (GATE da Fase 2)

| Evidência | Teste |
|---|---|
| Cobertura das 41 entidades listadas no Master Prompt | `tests/unit/test_modelo_canonico.py` |
| Toda entidade gera JSON Schema com `id/tenant_id/source/origin/classification` | idem |
| Defaults de classificação seguros | idem |
| Mapeamento B2B ON CRM → canônico, paginação, isolamento | `tests/unit/test_adapter_b2bon_crm.py` |
| **Paridade**: MAP (economia, risco por conta, funil) calculado pelo canônico = calculado pelo CRM interno | `tests/unit/test_map_canonico_paridade.py` |

A paridade é a validação mais forte: se o mapeamento perdesse dado
relevante (datas de cliente, estágio ganho, valor, NPS, interações),
os números do MAP divergiriam.

Ver também: `ENTITY_MAPPING.md`, `EVENT_MODEL.md`, `ADAPTER_CONTRACT.md`.
