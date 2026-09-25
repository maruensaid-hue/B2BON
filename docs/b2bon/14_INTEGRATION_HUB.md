# 14 — INTEGRATION HUB (fundação: Fase 3 · conectores: Fase 13)

## Componentes

| Componente | Código | Estado |
|---|---|---|
| Contrato de adapter (canônico) | `app/contexts/integrations/contract.py` | Fase 2 (ver `ADAPTER_CONTRACT.md`) |
| Registro de conectores | `app/contexts/integrations/registry.py` | `b2bon_crm` AVAILABLE; Salesforce, HubSpot, Pipedrive e RD Station CRM BETA (D-041) (Fase 13, um por vez) |
| Base HTTP dos conectores | `adapters/http_base.py` | Fase 13: 429/5xx → retry, 401/403 → `ErroCredencial` (sem retry), hosts fixos por conector (anti-SSRF), segredos mascarados em log e em erro de sync (D-043) |
| Conexões por tenant | tabela `conexao_integracao` (credenciais Fernet, nunca devolvidas pela API) | Fase 3 |
| Framework de sync | `app/contexts/integrations/sync.py` + tabela `execucao_sync` | Fase 3 |
| Adapter de payload (dados enviados na requisição) | `adapters/payload.py` | Fase 3 (base do MAP API para CRM externo) |
| Webhooks de saída (eventos de domínio) | `app/contexts/platform/webhooks.py` | Fase 3 |
| Webhooks de entrada (por conector) | — | TD-070 |
| OAuth / token refresh | `http_base.AcessoBearer`: refresh token, uma renovação por execução, persistida criptografada (Salesforce, HubSpot) | Fluxo de autorização OAuth pela UI: TD-068 |

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
| rate limits | 429 é transitório: `com_retry` com backoff; nenhuma leitura em paralelo |
| mapping | responsabilidade de cada adapter, documentada em `ENTITY_MAPPING.md` |
| OAuth / token refresh | por conector (seção abaixo) |
| webhooks de entrada / conflitos | TD-070 (conectores são somente leitura) |

## Webhooks de saída

- Eventos disponíveis: os de `TipoEvento` (`EVENT_MODEL.md`).
- Entrega: `POST` JSON com `id, type, version, tenant_id, aggregate, occurred_at, correlation_id, data`.
- Headers: `X-B2BON-Event`, `X-B2BON-Delivery`, `X-B2BON-Signature: t=<unix>,v1=<hmac_sha256("<t>.<corpo>")>`.
- Retry: 1, 5, 15, 60, 360 min. Desiste após 6 tentativas.
- **Barreira**: só eventos PUBLIC/INTERNAL são entregues. CONFIDENTIAL/RESTRICTED nunca saem.
- Disparo: `POST /cron/processar-eventos` a cada 15 min (GitHub Actions).

## O que o sync faz com os dados

O sync lê, conta e registra a execução (`destino` opcional). Os dados de
um CRM externo são consumidos **ao vivo pelo modelo canônico**: o MAP API
aceita `conexao_id` e calcula sobre a conexão (`CanonicalMapDataSource`),
com o mesmo resultado que o payload canônico (teste de paridade). Não há
upsert no CRM interno nem escrita de volta no CRM externo (D-041, TD-070).

## Habilitação dos conectores (D-041)

Conector implementado entra como **BETA** e aparece no hub, mas só conecta
quando o operador o lista em `CONECTORES_CRM_HABILITADOS` (ex.:
`salesforce`). Desabilitar bloqueia criação e sync de conexões existentes.
Motivo: os testes validam o formato documentado das APIs, não uma conta
real (a rede de desenvolvimento não alcança os provedores). Nada é
apresentado como disponível antes disso (§72).

API (admin): `GET /hub-integracoes/conectores` (com `conectavel`),
`POST /hub-integracoes/conexoes` (`credenciais` e `configuracao`),
`PUT /hub-integracoes/conexoes/{id}/credenciais` (reconectar),
`POST /hub-integracoes/conexoes/{id}/sincronizar/{entidade}`. Credencial
recusada (401/403) marca a conexão como `erro` até reconectar.

## Salesforce (conector 1/4 · BETA)

- **Auth**: `instance_url` (só `https://*.salesforce.com` / `*.force.com`)
  + `access_token`; opcional `refresh_token` + `client_id` (+ `client_secret`,
  `login_url` login/test.salesforce.com) para renovar o token.
- **Configuração**: `moeda` (ISO 4217, padrão BRL; org sem multi-moeda não
  informa moeda) e `campo_cnpj` (nome de API do campo customizado; validado
  para não injetar SOQL).
- **Leitura**: REST `/services/data/v60.0/query` (SOQL), paginação por
  `nextRecordsUrl`, incremental por `LastModifiedDate`.

| Salesforce | Canônico | Regra |
|---|---|---|
| Account | Organization + Account | `Website` → domínio; `NumberOfEmployees` → size; `BillingState` → region; `Type` com "Customer" → CUSTOMER, "Former" → CHURNED, resto PROSPECT; CNPJ só com `campo_cnpj` |
| 1ª Opportunity ganha da conta | Customer | `customer_since` = `CloseDate`; `churned_at` desconhecido (None) |
| Contact | Person + Contact | `HasOptedOutOfEmail` → `suppressed_at` (última alteração, data exata não existe no Salesforce); contato sem conta só vira Person |
| OpportunityStage (ativos) | PipelineStage | `IsWon` → WON, `IsClosed` → LOST, resto OPEN; um pipeline único |
| Opportunity | Opportunity | status por `IsWon/IsClosed`; `Amount` na moeda configurada; `closed_at` = `CloseDate` só se fechada; sem `AccountId` = descartada |
| Task / Event | Activity | `TaskSubtype` Call/Email; Event → MEETING; `WhatId` 006… → oportunidade |
| Task / Event com conta | Interaction `contato` | reclamação/elogio não são inferidos |
| Product2 | Offer | nome, família, descrição, ativo |
| — | CSMetric | não há objeto padrão de NPS: vazio |


## HubSpot (conector 2/4 · BETA)

- **Auth**: `access_token` (Private App ou OAuth); opcional `refresh_token`
  + `client_id` + `client_secret` (renova em `/oauth/v1/token`, guarda o
  refresh token novo). Host fixo `api.hubapi.com`; chave desconhecida nas
  credenciais é recusada.
- **Configuração**: `moeda` (quando o negócio não tem `deal_currency_code`)
  e `campo_cnpj` (propriedade interna da empresa).
- **Leitura**: CRM API v3, paginação por `after` (validado); incremental
  pela Search API (`GT` em epoch ms sobre `hs_lastmodifieddate`, ou
  `lastmodifieddate` em contatos); empresa do negócio pela Associations API
  v4 em lote (uma chamada por página).

| HubSpot | Canônico | Regra |
|---|---|---|
| Company | Organization + Account | `domain` sem `www.`; `numberofemployees` → size; `state` → region; `lifecyclestage` customer/evangelist → CUSTOMER, subscriber/lead/MQL → LEAD, SQL/opportunity → QUALIFIED, resto PROSPECT |
| Company cliente com `hs_lifecyclestage_customer_date` | Customer | sem a data, não vira Customer; `churned_at` desconhecido |
| Contact | Person + Contact | nome = first + last (ou e-mail); `hs_email_optout` → `suppressed_at`; empresa por `associatedcompanyid` |
| Deal pipeline / stage | Pipeline / PipelineStage | fechado com probabilidade 1.0 → WON, fechado → LOST, resto OPEN |
| Deal | Opportunity | status por `hs_is_closed_won`/`hs_is_closed`; probabilidade × 100; sem empresa associada = descartado |
| calls, emails, meetings, tasks, notes | Activity | tipo pelo objeto; HTML da nota removido; associação a empresa/negócio |
| engajamento com empresa | Interaction `contato` | lido uma vez por execução (o MAP pergunta conta a conta) |
| Product | Offer | nome, descrição |
| — | CSMetric | feedback/NPS do Service Hub: TD-071 |

## Pipedrive (conector 3/4 · BETA)

- **Auth**: `api_token` no header `x-api-token` (nunca na URL, que vai para
  log). Host fixo `api.pipedrive.com`. OAuth do Marketplace: TD-068.
- **Configuração**: `campo_cnpj` = chave (hash) do campo personalizado da
  organização.
- **Leitura**: API v1, paginação `start`/`limit` (`next_start`);
  incremental por `/recents?items=…&since_timestamp=` (UTC).

| Pipedrive | Canônico | Regra |
|---|---|---|
| Organization | Organization + Account | sem ciclo de vida no Pipedrive: `won_deals_count` > 0 → CUSTOMER, senão PROSPECT; sem domínio padrão (None); região = `address_admin_area_level_1` |
| 1º Deal ganho da organização | Customer | `customer_since` = `won_time`; churn desconhecido |
| Person | Person + Contact | e-mail/telefone principal; `marketing_status` unsubscribed → `suppressed_at` |
| Pipeline / Stage | Pipeline / PipelineStage | todo estágio é OPEN (ganho/perda é status do negócio) |
| Deal | Opportunity | `status` won/lost/open (deleted descartado); `closed_at` = `won_time`/`lost_time`; `lost_reason`; moeda do negócio; sem organização = descartado |
| Activity | Activity | call/email/meeting/task/deadline; demais tipos OTHER com o tipo original preservado |
| Activity concluída com organização | Interaction `contato` | lida uma vez por execução |
| Product | Offer | nome, categoria, descrição, ativo |

## RD Station CRM (conector 4/4 · BETA)

- **Auth**: `token` da instância. A API v1 só aceita o token na query
  (`?token=`): o filtro de log do `httpx` e o erro gravado pelo sync
  mascaram o valor (`token=***`, D-043). Host fixo `crm.rdstation.com`.
- **Configuração**: `moeda` (padrão BRL; a v1 não informa moeda) e
  `campo_cnpj` (`custom_field_id` do campo personalizado da organização).
- **Leitura**: API v1, paginação `page`/`limit` + `has_more`. **Sem sync
  incremental**: a v1 não filtra por data de alteração, então a capacidade
  é declarada falsa e o sync relê tudo (não se finge incremental).

| RD Station CRM | Canônico | Regra |
|---|---|---|
| Organization | Organization + Account | `url` → domínio; 1º segmento → industry; sem ciclo de vida: com negociação ganha → CUSTOMER, senão PROSPECT |
| 1ª negociação ganha | Customer | `customer_since` = `closed_at`; churn desconhecido |
| Contact | Person + Contact | primeiro e-mail/telefone; opt-out é do RD Station Marketing (não do CRM): `suppressed_at` desconhecido |
| Deal pipeline / stage | Pipeline / PipelineStage | todo estágio OPEN (ganho/perda é o `win` da negociação) |
| Deal | Opportunity | `win` true/false/null → WON/LOST/OPEN; `deal_lost_reason`; sem organização ou estágio fora dos funis = descartada |
| Task | Activity | call/email/meeting/visit/task; outros tipos (ex.: whatsapp) OTHER com o tipo preservado; conta pela negociação |
| Task concluída de negociação com organização | Interaction `contato` | lida uma vez por execução |
| Product | Offer | nome, descrição, visível |