# 14 — INTEGRATION HUB (fundação: Fase 3)

## Componentes

| Componente | Código | Estado |
|---|---|---|
| Contrato de adapter (canônico) | `app/contexts/integrations/contract.py` | Fase 2 (ver `ADAPTER_CONTRACT.md`) |
| Registro de conectores | `app/contexts/integrations/registry.py` | `b2bon_crm` AVAILABLE; Salesforce, HubSpot, Pipedrive, RD Station COMING_SOON |
| Conexões por tenant | tabela `conexao_integracao` (credenciais Fernet, nunca devolvidas pela API) | Fase 3 |
| Framework de sync | `app/contexts/integrations/sync.py` + tabela `execucao_sync` | Fase 3 |
| Adapter de payload (dados enviados na requisição) | `adapters/payload.py` | Fase 3 (base do MAP API para CRM externo) |
| Webhooks de saída (eventos de domínio) | `app/contexts/platform/webhooks.py` | Fase 3 |
| Webhooks de entrada (por conector) | — | Fase 13 |
| OAuth / token refresh | — | Fase 13 (credenciais já têm onde morar) |

## Checklist do §13 por conector (o que a fundação já dá)

| Requisito | Onde |
|---|---|
| credentials | `conexao_integracao.credenciais` (criptografado) |
| pagination | cursor opaco no contrato; `sync` percorre até o fim ou `max_paginas` |
| retries | `sync.com_retry`: backoff exponencial, só para `ErroTransitorio`/erro de transporte |
| idempotency | ids canônicos estáveis; escrita da API com `Idempotency-Key`; entrega de webhook única por (assinatura, evento) |
| synchronization | incremental por `updated_since` = início da última execução com sucesso |
| error handling | `execucao_sync.status/erro`; `conexao.ultimo_erro`; sync nunca derruba o chamador |
| observability | `execucao_sync` (itens, páginas, tentativas), logs com correlation id |
| rate limits | por provedor: Fase 13 (depende de cada API) |
| mapping | responsabilidade de cada adapter, documentada em `ENTITY_MAPPING.md` |
| OAuth / token refresh / webhooks de entrada / conflitos | Fase 13 |

## Webhooks de saída

- Eventos disponíveis: os de `TipoEvento` (`EVENT_MODEL.md`).
- Entrega: `POST` JSON com `id, type, version, tenant_id, aggregate, occurred_at, correlation_id, data`.
- Headers: `X-B2BON-Event`, `X-B2BON-Delivery`, `X-B2BON-Signature: t=<unix>,v1=<hmac_sha256("<t>.<corpo>")>`.
- Retry: 1, 5, 15, 60, 360 min. Desiste após 6 tentativas.
- **Barreira**: só eventos PUBLIC/INTERNAL são entregues. CONFIDENTIAL/RESTRICTED nunca saem.
- Disparo: `POST /cron/processar-eventos` a cada 15 min (GitHub Actions).

## O que o sync faz com os dados

Nesta fase, nada além de ler e contar (`destino` opcional). A decisão de
upsert no CRM interno, e a resolução de conflitos, é da Fase 13, conector
a conector.
