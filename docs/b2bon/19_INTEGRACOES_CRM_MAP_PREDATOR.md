# 19 — Integrações com CRMs externos para MAP e PREDATOR (plano)

- **Data**: 2026-10-02 · **Status**: IMPLEMENTADO para os 4 CRMs (D-087, 2026-10-04) — conectores em BETA até a
  validação em contas sandbox reais (§8.4)
- **CRMs**: Salesforce, HubSpot, Pipedrive e RD Station (CRM)
- **Base**: Integration Hub (`14_INTEGRATION_HUB.md`), contrato canônico (`ADAPTER_CONTRACT.md`), D-041/D-043

## 1. Onde estamos (fatos do código)

| O que já existe | Onde | Estado |
|---|---|---|
| Contrato canônico de CRM (leitura + escrita opcional `upsert_opportunity`/`add_note`, `writable_entities`) | `app/contexts/integrations/contract.py` | pronto |
| Adapters de **leitura** dos 4 CRMs (contas, contatos, funis, negócios, atividades, interações, produtos) | `app/contexts/integrations/adapters/{salesforce,hubspot,pipedrive,rd_station}.py` | **BETA, desligados** (`CONECTORES_CRM_HABILITADOS`) |
| Base HTTP segura: hosts fixos (anti-SSRF), retry em 429/5xx, 401/403 sem retry, segredos mascarados, refresh de token (Salesforce, HubSpot) | `adapters/http_base.py` | pronto |
| Conexões por tenant com credenciais criptografadas (Fernet), nunca devolvidas pela API | `conexao_integracao` | pronto |
| Sync incremental com retry, paginação e registro de execução | `integrations/sync.py`, `execucao_sync` | pronto |
| **MAP lê o CRM externo ao vivo** pelo modelo canônico (paridade testada com o CRM interno) | `map/data_source.py` (`CanonicalMapDataSource`) | pronto (depende do conector habilitado) |
| Webhooks de **saída** assinados (HMAC), com retry e barreira de confidencialidade | `platform/webhooks.py` | pronto |

**Lacunas** (já registradas): conectores nunca validados contra contas reais (TD-069); sem OAuth pela tela —
o admin cola tokens (TD-068); **somente leitura**: sem escrita no CRM, sem webhooks de entrada, sem resolução de
conflitos (TD-070); NPS/CS não lido (TD-071).

**Consequência**: para o **MAP**, falta validar e ligar. Para o **PREDATOR**, quase tudo é novo — o valor dele num
CRM externo é **escrever** (contas, contatos, atividades, reuniões, negócios).

## 2. O que cada módulo precisa do CRM do cliente

### MAP (saúde, risco e expansão das contas)
| Direção | Capacidade | Hoje |
|---|---|---|
| CRM → B2B ON | contas, clientes, contatos, funis, negócios, atividades, interações, produtos | existe (BETA) |
| CRM → B2B ON | NPS/CS (HubSpot feedback; Salesforce sem objeto padrão — campo configurável) | falta (TD-071) |
| CRM → B2B ON | frescor por evento (webhook de entrada → sync incremental daquele registro) | falta |
| B2B ON → CRM | **sinais do MAP no CRM**: health score e nível de risco em campos próprios da conta; tarefa de remediação para o dono da conta quando surgir `CustomerAtRisk`/`ChurnPredicted` | falta |

### PREDATOR (prospecção)
| Direção | Capacidade | Por quê |
|---|---|---|
| CRM → B2B ON | **deduplicação/supressão antes de prospectar**: não abordar quem já é cliente, tem negócio aberto ou pediu opt-out no CRM | evita abordar cliente atual e respeita LGPD |
| CRM → B2B ON | mapeamento de donos (owner do CRM ↔ vendedor B2B ON) | atribuição correta |
| B2B ON → CRM | **upsert de empresa e contato** qualificados (chave: CNPJ → domínio → e-mail) | o lead nasce no CRM do cliente, sem duplicar |
| B2B ON → CRM | **atividades da cadência** na linha do tempo (mensagem enviada, resposta, ligação) | histórico completo onde o time trabalha |
| B2B ON → CRM | **reunião agendada/qualificada → negócio** no funil/estágio configurado, com nota de resumo | o handoff SDR → AE acontece no CRM |
| B2B ON → CRM | opt-out recebido no B2B ON → marcado no CRM | supressão bidirecional |

## 3. Arquitetura (reuso, sem engine nova)

1. **Contrato**: ampliar as portas de escrita do `CrmAdapter` — `upsert_organization`, `upsert_person`,
   `log_activity`, `upsert_opportunity` (existe), `add_note` (existe), `set_suppressed` — declaradas em
   `writable_entities`; adapter que não suporta levanta `OperacaoNaoSuportada` (já é o padrão).
2. **Vínculo externo** (tabela nova `vinculo_externo`: tenant, conexão, entidade, id interno, id externo, versão):
   garante idempotência (reenvio não duplica) e permite atualizar em vez de recriar.
3. **Fila de saída por conexão**: os eventos de domínio que já existem (`TipoEvento` — `MessageApproved`,
   `MeetingCompleted`, `OpportunityCreated`, `CustomerAtRisk`, `ChurnPredicted`…) alimentam um consumidor por conexão
   (mesmo padrão do outbox de webhooks): retry com backoff, desistência após N tentativas com registro, reprocesso
   manual, e respeito ao limite de taxa de cada provedor.
4. **Webhooks de entrada** por conector, com verificação de assinatura do provedor e enfileiramento (nunca processar
   no request); o efeito é um sync incremental do registro alterado.
5. **Regra de conflito (proposta)**: o CRM do cliente é a fonte da verdade dos campos dele; o B2B ON **só escreve
   campos próprios** (ex.: `b2bon_health_score`, `b2bon_risco`, `b2bon_origem`), **cria** atividades/notas/negócios e
   **nunca sobrescreve** campos editados por pessoas. Isso elimina a maior parte dos conflitos.
6. **OAuth pela tela (TD-068)**: autorizar/callback com `state` anti-CSRF (e PKCE onde o provedor aceitar), escopos
   mínimos por módulo (leitura para MAP; escrita só se o tenant ligar o PREDATOR→CRM), tokens criptografados.
7. **Painel de sincronização** no Hub: última execução, itens, erros por registro, reprocessar.

## 4. Segurança e LGPD (inegociável)

- Escrita no CRM **desligada por padrão**, ligada por tenant e por capacidade (opt-in explícito do admin).
- Barreira existente: dado CONFIDENTIAL/RESTRICTED **nunca** sai (mesma regra dos webhooks de saída).
- Supressão/opt-out sempre vence: nada é escrito para contato suprimido; opt-out vai e volta.
- Minimização: só os campos necessários; nenhum dado de outro tenant; ambientes de demonstração bloqueados
  (D-083 já nega `hub-integracoes`).
- Auditoria de cada escrita (quem ligou, o que foi enviado, id externo); credenciais nunca devolvidas nem logadas.
- Hosts fixos por conector (anti-SSRF) e validação de campos configuráveis (anti-injeção, como o `campo_cnpj` do SOQL).

## 5. Fases

| Fase | Entrega | Tamanho | Depende de |
|---|---|---|---|
| **F1 — Validar leitura (TD-069)** | rodar os 4 adapters contra contas sandbox reais, corrigir divergências, testes de contrato com respostas reais anonimizadas; habilitar conector a conector → **MAP com CRM externo vai a GA** | M | contas sandbox (§7) |
| **F2 — OAuth pela tela (TD-068)** | conectar com 1 clique por provedor, escopos mínimos, reconectar, revogar | M | apps registrados em cada provedor (§7) |
| **F3 — Fundação de escrita** | portas de escrita no contrato, `vinculo_externo`, fila de saída por conexão, auditoria, painel de sync, kill-switch por conexão | G | F1 |
| **F4 — PREDATOR → CRM** | dedup/supressão antes de prospectar; upsert empresa/contato; atividades da cadência; reunião → negócio; opt-out bidirecional; mapeamento de donos | G | F3 |
| **F5 — MAP bidirecional** | webhooks de entrada (frescor), NPS/CS (TD-071), health score/risco em campos próprios + tarefa de remediação | M | F3 |
| **F6 — GA** | docs, tour, FAQ, entitlement por plano, métricas de uso | P | F4/F5 |

**Ordem sugerida dos conectores em cada fase**: HubSpot → Pipedrive → Salesforce → RD Station CRM (HubSpot tem
upsert por propriedade única e webhooks maduros; RD Station CRM v1 não filtra por data de alteração, então o
incremental depende de webhooks — avaliar a API mais nova do RD Station na F1). A ordem real deve seguir os CRMs
que os clientes e prospects usam (§7).

Cada fase termina como as anteriores: testes (contrato, idempotência, isolamento por tenant, demo bloqueada,
Postgres), E2E, medição, docs (14, ENTITY_MAPPING, DECISIONS, CHANGELOG) e só então habilitação.

## 6. Testes

- **Contrato por adapter**: respostas gravadas do provedor (formato real, anonimizado) → modelo canônico e o inverso
  para escrita.
- **Idempotência**: o mesmo evento enviado duas vezes gera um único registro no CRM (via `vinculo_externo`).
- **Segurança**: escrita desligada por padrão; RESTRICTED nunca sai; contato suprimido não é escrito; webhook de
  entrada com assinatura inválida é recusado; demo não alcança o Hub.
- **Sandbox real** (manual a cada release do conector; opcional em CI com segredos): conectar, sincronizar, escrever,
  conferir no CRM.
- **Paridade MAP**: o mesmo resultado com dados vindos do CRM interno e do externo (teste que já existe, estendido).

## 7. Decisões do PO (abrem OI-030)

1. **Prioridade dos CRMs**: quais seus clientes/prospects usam mais? (define a ordem das fases)
2. **RD Station**: integrar só o **RD Station CRM** ou também o **RD Station Marketing** (opt-out/leads de marketing)?
3. **Fonte da verdade**: confirmar a regra do §3.5 (B2B ON só escreve campos próprios, cria atividades/negócios e
   nunca sobrescreve campos editados por pessoas).
4. **O que o PREDATOR escreve**: empresa + contato + atividades + negócio na reunião? Em que funil/estágio?
5. **Escrita opt-in por tenant** (recomendado) ou ligada por padrão?
6. **Contas sandbox e apps OAuth**: criar/ceder contas de teste e registrar os apps (Salesforce Connected App,
   HubSpot app, Pipedrive Marketplace app, RD Station app) em nome da CyberFort.
7. **Comercial**: integração com CRM externo entra em algum plano/entitlement específico? (preço não é definido aqui)

## 8. Implementação (D-087, 2026-10-04)

Pedido do PO: "Faça para os 4 CRMs indicados". As decisões 2–5 e 7 do §7 seguiram as recomendações deste plano
(revisáveis): RD Station **CRM**; regra do §3.5; PREDATOR escreve empresa + contato + atividades + negócio na reunião;
escrita opt-in por conexão; entitlement do Hub (sem preço novo). A decisão 6 (sandbox e apps OAuth) segue com o PO.

### 8.1 O que cada CRM faz

| | Salesforce | HubSpot | Pipedrive | RD Station CRM |
|---|---|---|---|---|
| Conectar com 1 clique | OAuth + PKCE (produção e sandbox) | OAuth | OAuth (domínio da empresa) | — (token da instância) |
| Procura antes de criar | Account por CNPJ/Website; Contact por e-mail (SOQL escapado) | empresa por CNPJ/domínio; contato por e-mail (Search API) | organização por CNPJ/nome exato; pessoa por e-mail | organização por nome exato; contato por e-mail |
| Negócio na reunião | Opportunity (StageName + CloseDate do prazo configurado) + papel do contato | deal (pipeline/estágio) com associações | deal (stage_id) | negociação (deal_stage_id) |
| Atividades | Task concluída / Event (reunião) | e-mail, ligação, reunião, nota (WhatsApp/LinkedIn como nota) | activity concluída / nota (HTML escapado) | anotação **só dentro de negociação** |
| Tarefa de resgate (MAP) | Task aberta, prioridade alta | task | activity "task" em aberto | não (exige negociação) — o sinal é gravado |
| Opt-out | `HasOptedOutOfEmail` + campo próprio opcional | propriedade `b2bon_opt_out` | campo próprio (ou `marketing_status`) | campo personalizado próprio (obrigatório) |
| Campos próprios | criados pelo admin (ex.: `B2BON_Score_Risco__c`) | criados pela B2B ON (`preparar-campos`) | criados pela B2B ON (`preparar-campos`) | criados pelo admin (`custom_field_id`) |
| NPS (TD-071) | campo da Account (`campo_nps`) | propriedade da empresa | campo da organização | campo personalizado da organização |

### 8.2 Fluxos

- **PREDATOR → CRM**: mensagem de cadência enviada → atividade; reunião agendada → negócio (um por conta) + reunião;
  resultado/qualificação da reunião → nota; opt-out → CRM; "Enviar ao CRM" na ficha da conta → empresa + contatos.
- **CRM → PREDATOR**: índice de hashes (CNPJ, domínio, e-mail) com cliente / negócio aberto / opt-out, refeito 1x/dia e
  após webhook de entrada; o envio cancela a mensagem e importa o opt-out.
- **MAP ↔ CRM**: NPS lido do campo configurado; score/nível de risco gravados nas contas-cliente quando mudam; conta
  crítica → tarefa para o dono (no máximo 1 por conta por mês).
- **Rotinas**: `POST /cron/integracoes-crm` (15 min: webhooks de entrada + fila de escrita) e
  `POST /cron/integracoes-crm-diario` (06:00 UTC: índices + sinais do MAP), no workflow `cron-envios.yml`.

### 8.3 Segurança (como §4 pedia)

Escrita desligada por padrão e por capacidade; interruptor geral `ESCRITA_CRM_ATIVA` e pausa por conexão; contato com
opt-out nunca escrito; demo nunca enfileira; vínculo por passo (sem duplicar em retentativa); auditoria de cada escrita e
de cada desistência; índice só com hashes; OAuth com `state` cifrado e conclusão pelo mesmo usuário; credencial
`oauth_app` não pode ser colada; webhook de entrada com token de 256 bits (só o hash no banco) que só marca a conexão;
hosts fixos, ids validados antes de URL/SOQL, SOQL escapado, HTML escapado, erros curtos e mascarados.

### 8.4 Para liberar a um cliente (checklist do operador)

1. Criar contas sandbox de cada CRM e validar leitura + escrita de ponta a ponta (TD-069); ajustar o que divergir.
2. Registrar os apps OAuth da CyberFort e preencher no Render: `OAUTH_SALESFORCE_CLIENT_ID/SECRET`,
   `OAUTH_HUBSPOT_CLIENT_ID/SECRET`, `OAUTH_PIPEDRIVE_CLIENT_ID/SECRET`. Redirect URI de cada app:
   `https://b2bon-api.onrender.com/api/v1/hub-integracoes/oauth/<sistema>/callback`. HubSpot: escopos da lista em
   `integrations/oauth.py`; Pipedrive: escopos de leitura/escrita de deals, contacts, activities e notes no Marketplace.
3. Liberar o conector em `CONECTORES_CRM_HABILITADOS` (ex.: `hubspot,pipedrive`).
4. No cliente: conectar, abrir "Escrita no CRM", escolher funil/estágio, criar/informar os campos próprios, ligar a
   capacidade desejada, e (opcional) cadastrar a URL de webhook no CRM.

