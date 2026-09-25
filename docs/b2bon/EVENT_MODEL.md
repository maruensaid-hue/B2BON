# EVENT MODEL (Fase 2, Master Prompt §77)

Código: `app/contexts/shared/events.py`, tabela `evento_dominio`
(migração `1ca76a6cdfbc`).

## Envelope

| Campo | Significado |
|---|---|
| evento_id | UUID v4, único (idempotência de consumidores) |
| tipo | `TipoEvento` (PascalCase, ex.: `OpportunityCreated`) |
| versao | versão do schema do payload (começa em 1) |
| tenant_id | dono do evento; consumidores nunca cruzam tenant |
| agregado_tipo / agregado_id | entidade que mudou |
| ator_id | usuário que causou (None = sistema/regra) |
| classificacao | `DataClassification`; controla quem pode consumir (barreira Buy/Sell na Fase 10) |
| correlation_id | liga ao request de origem (Fase 3 preenche) |
| payload | dados mínimos (ids e valores), nunca documento inteiro nem PII desnecessária |
| ocorrido_em / processado_em / tentativas / ultimo_erro | controle do outbox |

## Garantias

1. **Atomicidade**: `publicar` faz `add + flush` na sessão do chamador.
   O evento só existe se a mudança de negócio for commitada.
2. **Entrega pelo menos uma vez**: `processar_pendentes` marca
   `processado_em` só depois de todos os handlers rodarem. Handlers
   devem ser idempotentes por `evento_id`.
3. **Falha isolada**: exceção num handler incrementa `tentativas` e
   guarda `ultimo_erro`, sem travar a fila. Desiste após `MAX_TENTATIVAS=5`
   (o evento continua na tabela para análise).
4. Fora do caminho da requisição: o disparo do dispatcher é por cron
   (ligado na Fase 3).

## Eventos publicados hoje

| Evento | Onde | Payload |
|---|---|---|
| OpportunityCreated | `crm_service.criar_negocio` | conta_id, valor, estagio_id |
| OpportunityStageChanged | `crm_service.mover_estagio` | conta_id, estagio_id, tipo_estagio |
| CustomerCreated | `crm_service.mover_estagio` (1º ganho da conta) | negocio_id |
| MessageApproved | `aprovacao_service.aprovar`, `aprovar_lote`, auto-aprovação por regra | canal, decisor_id, cadencia_id |

## Catálogo (declarado, publicado nas fases que criam o fluxo)

MeetingCompleted, CustomerAtRisk, ChurnPredicted, RemediationCreated,
IntentCreated, BusinessMatchCreated (7–8), BidDiscovered, BidAnalyzed (9),
ProcurementDemandCreated, ProcurementPlanUpdated,
ProcurementProcessCreated, ContractExpiring, SupplierRiskDetected (10),
AIRecommendationCreated/Accepted/Rejected (4/6).
