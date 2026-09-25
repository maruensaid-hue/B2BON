# ADAPTER CONTRACT (Fase 2, Master Prompt §13)

Código: `app/contexts/integrations/contract.py`.

## Interface

`CrmAdapter` (ABC). Todo método recebe `tenant_id` e só pode devolver
dados desse tenant.

| Método | Retorno | Observação |
|---|---|---|
| `capabilities()` | `AdapterCapabilities(system, readable_entities, writable_entities, incremental_sync, webhooks)` | o domínio decide pelo que o adapter declara, nunca por `if sistema == ...` |
| `list_organizations/accounts/people/opportunities(tenant_id, cursor, updated_since, limit)` | `Page[T]` | cursor opaco; `updated_since` para sync incremental |
| `list_customers/contacts/activities/cs_metrics(tenant_id, cursor, limit)` | `Page[T]` | |
| `list_interactions(tenant_id, account_id, cursor, limit)` | `Page[Interaction]` | filtro por conta |
| `list_pipelines/list_stages/list_offers(tenant_id)` | `list[T]` | volumes pequenos |
| `upsert_opportunity`, `add_note` | id no sistema de origem | opcionais; default levanta `OperacaoNaoSuportada` |

`iterar_todos(listar, tenant_id)` consome todas as páginas.

## Obrigações de todo adapter

1. **Isolamento**: nenhum item de outro tenant (teste de contrato obrigatório).
2. **Proveniência**: todo item com `SourceRef` preenchido e id canônico estável.
3. **Não inventar**: campo ausente na origem = `None`.
4. **Classificação**: marcar PUBLIC só o que é público na origem.
5. **Declarar capacidades**: operação não declarada levanta `OperacaoNaoSuportada`.

## Fase 3 acrescenta (fora deste contrato de dados)

Credenciais/OAuth/refresh por conexão, retries com backoff, rate limit
por provedor, webhooks de entrada, idempotência de escrita,
observabilidade, registro de conectores e framework de sync.

## Implementações

| Adapter | Fase | Status |
|---|---|---|
| `B2BOnCrmAdapter` (`adapters/b2bon_crm.py`) | 2 | leitura completa das entidades comerciais usadas pelo MAP |
| Salesforce, HubSpot, Pipedrive, RD Station | 13 | — |

## Consumidor de referência

`CanonicalMapDataSource` (MAP) aceita qualquer `CrmAdapter`. Validado
por paridade contra o CRM interno (`tests/unit/test_map_canonico_paridade.py`).
