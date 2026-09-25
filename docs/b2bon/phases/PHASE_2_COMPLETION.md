# PHASE 2 — CANONICAL BUSINESS MODEL · Completion Report

- **Data**: 2026-09-25 · **Branch**: `staging` · **Autorização**: PO (autorização geral das Fases 1–17)

## 1. Entregas

| Item exigido (§84 Fase 2) | Entrega |
|---|---|
| Commercial Canonical Model | `app/contexts/shared/canonical/commercial.py`: 21 entidades + enums (inclui os 11 estados de mensagem do §17 e Offer Intelligence do §25) |
| Procurement Canonical Model foundation | `app/contexts/shared/canonical/procurement.py`: 20 entidades, `EvidenceRef`, default CONFIDENTIAL para dado interno do comprador |
| Base | `base.py`: `SourceRef`, `DataOrigin` (§42), `DataClassification`, `canonical_id` |
| Mapear B2B ON CRM → canônico | `app/contexts/integrations/adapters/b2bon_crm.py` (`B2BOnCrmAdapter`), leitura de 12 entidades com paginação por cursor e `updated_since` |
| Adapter contract | `app/contexts/integrations/contract.py` (`CrmAdapter`, `Page`, `AdapterCapabilities`, `OperacaoNaoSuportada`) |
| Eventos de domínio | `app/contexts/shared/events.py` + tabela `evento_dominio` (outbox transacional); publicados: OpportunityCreated, OpportunityStageChanged, CustomerCreated, MessageApproved |
| MAP sobre o canônico | `CanonicalMapDataSource`: MAP roda sobre qualquer `CrmAdapter` |
| ENTITY_MAPPING.md / EVENT_MODEL.md / ADAPTER_CONTRACT.md | criados; `04_CANONICAL_MODEL.md` escrito |

## 2. GATE — modelo validado

| Critério | Resultado |
|---|---|
| Cobertura das 41 entidades do §12 | ✅ `test_modelo_canonico.py` |
| JSON Schema com proveniência e classificação para todas | ✅ (41 casos parametrizados) |
| Mapeamento, ciclo de vida, paginação | ✅ `test_adapter_b2bon_crm.py` |
| Isolamento do adapter (tenant A nunca vê B) | ✅ |
| **Paridade MAP: economia, risco por conta e funil iguais pelo CRM interno e pelo canônico** | ✅ `test_map_canonico_paridade.py` |
| Outbox atômico, dispatcher, retry com limite | ✅ `test_eventos_dominio.py` |
| MessageApproved só com aprovação humana | ✅ `test_aprovacoes.py::test_aprovar_publica_message_approved_e_rejeitar_nao` |
| Suite completa | ✅ **1.592 passed** (Fase 1: 1.530) |
| Migração em SQLite (teste) e Postgres 16 (upgrade/downgrade/upgrade) | ✅ `1ca76a6cdfbc` |
| CI da Fase 1 em `staging` | ✅ run 36151084250: success |

Sem mudança de frontend, preço ou plano nesta fase.

## 3. Riscos e pendências

- Revision id "legível" colidiu com migração existente; corrigido e virou regra (D-012).
- TD-041: eventos só em 3 fluxos; dispatcher sem gatilho até a Fase 3.
- TD-042: fonte canônica do MAP carrega tudo em memória.
- OI-001 continua aberta.

## 4. Próxima fase

**PHASE 3 — API & INTEGRATION FOUNDATION.**
