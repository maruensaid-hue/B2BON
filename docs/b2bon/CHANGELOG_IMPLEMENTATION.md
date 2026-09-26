# CHANGELOG — IMPLEMENTATION

## Phase F — Business Network e acesso do fornecedor (2026-09-26, autorizada pelo PO)

- Link de acesso por participante (mostrado uma vez; só o hash é guardado) para o fornecedor responder sem login e sem ocupar assento.
- Empresas da rede veem "Convites de compra" na própria conta e respondem por lá.
- Portal: convite, requisitos, itens, esclarecimentos (publicados sem dizer quem perguntou), perguntas, proposta, anexos e declínio.
- Comprador responde esclarecimentos, vê propostas enviadas pelo fornecedor e baixa anexos.
- Migração `e1b3d5f7a9c0`: esclarecimentos, anexos, acesso do participante, canal da proposta.

## Phase E — Enterprise Strategic Sourcing (2026-09-26, autorizada pelo PO)

- Novo módulo Strategic Sourcing (`/sourcing`, menu próprio): RFP, RFQ, RFI, EOI, concorrência privada, qualificação e evento estratégico.
- Descoberta de fornecedores (cadastro interno + perfis públicos da rede), convite, respostas e propostas por rodada, avaliação por requisito com peso, comparação sem vencedor automático, shortlist, negociação, aprovação por administrador, adjudicação e contrato.
- Migração `d8a0c2e4f6b7`: participante, item, proposta, preço por item e avaliação no modelo unificado, com lado imutável; peso no requisito.
- Correção: o menu lateral de desktop agora mostra Licitações e Compras públicas (antes só no menu mobile).

## Phase D — Public buy side (2026-09-26, autorizada pelo PO)

- Sinais de risco, workspace do processo, Supplier 360, ranking e ferramenta do agente sem uma consulta por processo/contrato (TD-090).
- Workspace do processo mostra as próximas etapas pelo workflow e os documentos que a Lei 14.133 espera na etapa atual.
- Cadastro do comprador sem campo obrigatório responde 422 com o nome do campo.
- Barreira Buy/Sell testada nas superfícies novas, nos dois sentidos.

## Phase C — Sell side: Public Bid + Enterprise Bid (2026-09-26, autorizada pelo PO)

- Enterprise Bid por configuração: RFI, RFQ e concorrência privadas, além do RFP privado.
- Workflow `ENTERPRISE_RFP_SELL@2` com negociação depois da proposta enviada; a tela pergunta ao workflow o que dá para fazer.
- Go/No-Go v2: requisito obrigatório não atendido bloqueia.
- Resposta por requisito/pergunta (migração `c6f8a0b2d4e5`) e esboço de proposta sem IA (JSON/Markdown) com pendências e anexos do cofre.
- `ProcessWorkspace`: abas compartilhadas por licitação e processo de compra.
- E2E: sessão de login reaproveitada (rate limit do login preservado) e spec nova do workspace.

## Phase B — Document & Requirement Engine (2026-09-26, autorizada pelo PO)

- Requisito normalizado com obrigatoriedade (obrigatório / desejável / UNKNOWN) lida da linguagem do trecho literal, igual para edital, TR, RFP e documento do comprador.
- Regra de proveniência do requisito digitado por humano no engine compartilhado.
- Migração `b4e6f8a0c2d3`: coluna `obrigatorio` em `requisito_licitacao` e `requisito_sourcing` (anteriores ficam UNKNOWN).
- Matriz de conformidade e tela de requisitos mostram "Obrigatório"/"Desejável".

## Phase A — Foundation do plano unificado (2026-09-26, autorizada pelo PO)

- Workflow e ruleset resolvidos num ponto só por (lado, segmento, tipo de processo), com falha fechada sem vínculo.
- Ruleset com versão, vigência e fonte; Lei 14.133 vigente desde 2021-04-01.
- Espelho: eventos do ORM e backfill num instalador único do núcleo; cada lado declara só o mapeamento.
- Orçamento de desempenho (`tests/desempenho`, baseline em `docs/b2bon/perf/`) e análise de duplicação (`scripts/qualidade/duplicacao.py`).
- Sem mudança de schema, de API ou de tela; nenhuma regressão de consultas ou latência.

## Sourcing S4 — workflow e rulesets declarativos (2026-09-26, autorizada pelo PO)

- Motor neutro `sourcing/workflow.py` e `sourcing/ruleset.py`, com registro por código versionado.
- `PUBLIC_TENDER_SELL@1`, `ENTERPRISE_RFP_SELL@1`, `PRIVATE_RFP@1` (vendedor) e `PUBLIC_PROCUREMENT_BUY@1`, `PUBLIC_PROCUREMENT_BR_14133@1` (comprador) no lugar das tuplas de status, de `DOCUMENTOS_ESPERADOS` e das constantes da Lei 14.133.
- Mudança de status, decisão Go/No-Go, registro de resultado e atualização de processo validam pelo workflow; mesmas mensagens e respostas.
- Espelho grava os códigos do registro. Nenhuma mudança de schema.

## OI-019 resolvido — produtos por job-to-be-done (2026-09-26, documentação)

- D-059: B2B ON Bid Intelligence (Public + Enterprise Bids, R$ 1.490, 25K AI Credits), Strategic Sourcing (R$ 2.990, 5 buyer users, 50K), Strategic Sourcing Enterprise (a partir de R$ 5.990, 100K), Public Procurement (preço pendente).
- Especificação do catálogo, fonte única, entitlements, estado real das capacidades e barreira por camada. OI-019 e OI-015 resolvidos; OI-021 (implementação comercial) e OI-022 (seat adicional, bundles) abertos.
- Nenhum código comercial alterado: a fase corrente (S4) só permite documentação.

## Sourcing S3 — schema unificado (expand) (2026-09-26, autorizada pelo PO)

- Migração `a3d5f7b9c1e2`: `processo_sourcing`, `documento_sourcing`, `requisito_sourcing`, `contrato_sourcing`, `evento_sourcing`, `evento_contrato_sourcing`; `lado` imutável (trigger SQLite/Postgres + ORM).
- Espelho das tabelas antigas por eventos do ORM, em SAVEPOINT; backfill idempotente em lotes por `/cron/sourcing-sincronizar`.
- Leitura dupla com comparação nos repositórios (`SOURCING_LEITURA_DUPLA`); a suíte inteira roda em modo ESTRITO.
- Fitness: tabelas unificadas só pelo núcleo; `Lado.COMPRA` só no comprador e `Lado.VENDA` só no vendedor.
- Tabelas antigas continuam a fonte da verdade.

## Sourcing S0–S2 (2026-09-26, autorizadas pelo PO)

- S0: documentos sem carregar arquivo/texto em listagens (colunas deferidas); sinais de risco sem N+1; paginação por cursor keyset em licitações e cadastros do comprador, com "Carregar mais".
- S1: núcleo `contexts/sourcing` (Requirement Engine com perfis, Document Engine, Evaluation Engine com direção) usado por Bids e Procurement; `shared/matching` com a estratégia de ICP única (corrige o fit da rede com CNAE pontuado).
- S2: repositórios por lado com lado fixo; FinOps e Analytics leem a venda pelo repositório; fitness nova da barreira junto com a antiga.
- Nenhuma mudança de schema.

## Correção arquitetural — Strategic Sourcing & Bids (2026-09-26, só documentação)

- Quatro segmentos explícitos (B2B Sales · Public Sector Bids · Public Procurement · Enterprise Strategic Sourcing; Enterprise Bids como metade vendedora do Enterprise), entregues por engines compartilhados.
- Auditoria: gaps de negócio (Enterprise só como enum; buy side privado inexistente), 7 duplicações entre `bids` e `procurement`, regras fixas, 5 problemas de performance.
- Desenho: `SourcingProcess` + filhos compartilhados, Requirement/Evaluation/Matching/Workflow/Ruleset, barreira por repositório com lado, API `/sourcing/{sell|buy}`, UI `ProcessWorkspace`, capabilities de IA.
- Novo `18_STRATEGIC_SOURCING.md`; seções de correção em 00, 02–06, 10, 12–14; D-055; OI-019/020; TD-081–086. Nenhum código, schema, UI, workflow, agente ou integração alterado.

## Fase 17 — Scale, Security & Hardening (2026-09-25)

- Varredura de isolamento sobre todas as rotas GET (tenant × tenant e Buy × Sell).
- Prompt injection: tag antiga neutralizada, mensagem de lead e atividades delimitadas; suíte ponta a ponta.
- Teto de IA em 9 rotas que não tinham; fitness function para todas.
- 92 índices de FK (migração `c4f1a9e7d2b3`) + fitness function.
- Teste de carga (script) e correção de N+1 no MAP (p95 geral 1.464 → 507 ms).
- Verificação de backup/restore (script) e runbook de DR. Log de requisição lenta; cache no catálogo público.
- Dependências: 0 vulnerabilidades (fast-uri atualizado no lockfile).

## Fase 16 — Analytics & Revenue Intelligence (2026-09-25)

- Contexto `analytics`: 9 métricas de receita do lado vendedor + risco de renovação de contratos públicos (com Bid Intelligence). `GET /inteligencia/receita/metricas`.
- Procurement: ciclo de contratação, execução do PCA, desempenho de fornecedores, risco de renovação. `GET /procurement/metricas`.
- Toda métrica com metodologia e amostra; nada estimado. UI: CRM → Revenue Intelligence; indicadores em Compras públicas. Sem migração.

## Fase 15 — Pricing, AI Credits & Commercial Monetization (2026-09-25)

- Desbloqueada pelo PO com o prompt da Fase 15 (antes: bloqueada, D-045).
- Catálogo versionado de pacotes (AI Start … AI 1M, Enterprise sob consulta) e de workloads (`CREDIT_CATALOG_V1`, classes C0–C3, pesos do PO).
- Carteira por lotes com validade e FEFO; extrato `CREDIT_*` idempotente; reserva → liquidação/liberação/estorno; franquia mensal sem rollover.
- AI Gateway: execução por workload, confirmação acima de 100 créditos, budget guard, cost guard, cache de resposta, evento de uso com workload/versão/cache.
- Compra de créditos pelo checkout existente + webhook assinado (valor conferido, idempotente); recarga automática com consentimento; excedente Enterprise.
- Economia: receita, custo, margem (alvo 80%, alerta 75%, crítico 65%), alertas por janela e amostra, matriz de rentabilidade, recomendações de peso (nunca aplicadas sozinhas), economia unitária, valor de negócio, relatório de calibração 7/30/90.
- UI: página AI Credits do cliente, AI FinOps (super_admin), seção de vendas e página "Como funcionam os AI Credits"; confirmação de consumo na análise de edital.
- Migração `e7b3c1a9f5d2`: saldos da Fase 5 viram lote ADJUSTMENT com reconciliação. Cron `/cron/creditos-ia`.
- Preço-base do Public Procurement e franquias Procurement/Full Suite seguem pendentes (OI-017).

## Fase 14 — Product Catalog, Plans & Sales Page (2026-09-25)

- Catálogo comercial (`platform/catalogo.py`) com os 10 produtos do escopo e estado de cada um; `GET /catalogo` público e `GET /assinatura` do tenant.
- Página pública: catálogo com estado e comparativo de recursos por plano; preços existentes inalterados.
- Área interna "Assinatura": plano, módulos, uso do mês, IA e conectores.
- Public Procurement: PENDING_DEFINITION, sem botão de compra, estrutura de precificação vazia. Guarda de preços preservados. Sem migração.

## Fase 13 — External CRM Connectors (2026-09-25)

- Conector 1/4 **Salesforce** (BETA, desligado por padrão): leitura de contas, contatos, estágios, oportunidades, clientes, tarefas/eventos e produtos; incremental; renovação de token; anti-SSRF.
- Hub: credenciais e configuração na conexão (criptografadas, nunca devolvidas), reconexão, `conectavel` por conector, conexão com credencial recusada fica `erro`.
- MAP API aceita `conexao_id` (mesmo resultado que o payload canônico). Tela de conexões no admin de API. Sem migração.
- Conector 2/4 **HubSpot** (BETA, desligado por padrão): empresas, contatos, pipelines, negócios (empresa via Associations v4), engajamentos e produtos; incremental pela Search API; renovação OAuth. Renovação de token extraída para `AcessoBearer` (comum aos conectores).
- Conector 3/4 **Pipedrive** (BETA, desligado por padrão): organizações, pessoas, funis, negócios, atividades e produtos; incremental por `/recents`; token só no header.
- Conector 4/4 **RD Station CRM** (BETA, desligado por padrão): organizações, contatos, funis, negociações, tarefas e produtos; sem incremental (a API v1 não permite, e isso é declarado). Segredos mascarados em log e em erro de sync.

## Fase 12 — Advanced Agent Orchestration (2026-09-25)

- B2B ON Intelligence Agent: pergunta → agente especialista → ferramenta; 13 ferramentas registradas pelos contextos (Shared Kernel).
- Permissões: ferramenta declarada, agente autorizado, módulo do plano, papel; READ executa, WRITE/EXTERNAL viram proposta, SENSITIVE é recusada; tenant sempre do usuário; compra × venda não se misturam.
- Fallback por IA (C1, medido) vendo só o catálogo permitido. Painel no Cérebro Corporativo. Sem migração.

## Fase 11 — Corporate Rooms & Buying Rooms (2026-09-25)

- Participantes por usuário (EDITOR/LEITOR), documentos com hash, tarefas, reuniões e comitê de compra na sala, cada um com escopo compartilhado/interno.
- Correção de exposição: o comprador deixa de ver o nome interno e o estágio do negócio do vendedor; vê título e fase compartilhados.
- Painel da sala no modal. Migração `855accb19354`.

## Fase 10 — Public Procurement / Buy Side (2026-09-25)

- Contexto `app/contexts/procurement/` e API `/api/v1/procurement/*` (módulo `procurement`, preço PENDING_DEFINITION, fora de todos os planos).
- Órgãos, unidades, demandas (aprovação por admin, análise para revisão), PCA com painel, processos com workspace e auditoria, fornecedores (Supplier 360), contratos e eventos, pesquisa de preços, documentos com IA ancorada.
- Motor de risco (11 sinais, "requer revisão") e próxima ação.
- Barreira Buy/Sell: fitness function estrutural + teste crítico §80 (acesso, recuperação, vazamento, IA indireta, mesmo tenant).
- Shared Kernel: extração de documentos e grounding usados por Bids e Procurement.
- UI: Compras públicas. Migração `815caa6c49f8`. Nenhum preço criado ou alterado.

## Fase 9 — Bid Intelligence / Sell Side (2026-09-25)

- Contexto `app/contexts/bids/` e API `/api/v1/bids/*` (módulo `bids`, fora de todos os planos até decisão do PO).
- Licitações, documentos com hash e texto por página, Tender/TR Analyzer (IA C3) com proveniência calculada pelo sistema.
- Matriz de conformidade, Go/No-Go (decisão humana), cofre com validade, Deadline Engine, concorrência, contratos ganhos, grafo de procurement.
- Fonte PNCP experimental e desligada. Dependência nova: `pypdf`.
- UI: Licitações e Workspace. Migração `5ddf7b14a837`. Nenhum preço criado ou alterado.

## Fase 8 — Network Intelligence (2026-09-25)

- Sinal → CRM (conta + negócio) ou → PREDATOR (conta) sem duplicação: reaproveita conta/negócio, fecha os sinais irmãos, sinal novo de empresa convertida já nasce convertido.
- Intent Intelligence do lado vendedor (`intent_compativel`), Relationship Intelligence (força com motivos).
- Privacidade no matching: bloqueadas e ocultas fora; aresta privada não vira sinal; matches não revelam conexões/relacionamentos de terceiros.
- Corporate Rooms: só leitura sem conexão ativa. Migração `6a6ea43222b8`.

## Fase 7 — Business Network Foundation (2026-09-25)

- Contexto `app/contexts/network/`: Company Identity (`empresa_rede`), Company Claim, Membership, Business Graph com as propriedades do §28, regra única de privacidade.
- Relacionamento com empresa fora da rede por CNPJ; reivindicação por empresa verificada com o mesmo CNPJ.
- Privacidade: aresta privada deixa de aparecer para a empresa citada; visibilidade `conexoes` implementada; bloqueio esconde feed, intents e arestas; empresa pode sair do diretório.
- Membership: identidade pública da empresa só por admin (D-026).
- UI: card "Identidade da empresa na rede". Migração `7dc1428d524f` (com backfill).

## Fase 6 — Opportunity Intelligence (2026-09-25)

- Contexto `app/contexts/opportunity/`: Discovery Gap, Next Best Offer, Next Best Action, White Space, sinais de compra, riscos e stakeholders faltantes, todos determinísticos e explicáveis.
- Need Extraction por IA (`opportunity.extracao_necessidades`) com citação literal obrigatória e revisão humana; Opportunity Agent ativo.
- Offer Intelligence (§25) na oferta; campos novos no formulário de ofertas.
- Card "Inteligência da oportunidade" na tela do negócio. API `/api/v1/inteligencia/oportunidades/*`.
- C7: riscos de pipeline e sugestões de expansão liberados para CRM (D-023).
- Migração `a8390a098f04`. Nenhum preço ou plano alterado.

## Fase 5 — AI FinOps & Credits (2026-09-25)

- Custo do provedor por chamada (tabela `preco_modelo_ia` versionada, 6 modelos).
- Créditos: política `PENDING_DEFINITION` (taxa a definir pelo PO), carteira por tenant, extrato, excedente.
- Orçamentos/quotas por tenant/módulo/feature com bloqueio antes do provedor.
- Dashboard FinOps (super_admin, USD) e consumo do tenant (créditos, sem USD). UI: Admin → IA & Créditos.
- Migração `f892ebf6e6f9`.

## Merge paralelo (2026-09-25)

- Integradas as features de outra sessão (captura pública de lead, representantes com comissão, e-mail de notificação da Rede). Migração de merge `b53c1ac42468`.

## Fase 4 — AI Intelligence Foundation (2026-09-25)

- AI Gateway único (14/14 chamadas), roteador C0–C3, registro de features/agentes/ferramentas.
- Correção: `temperature` não é mais enviada a modelos que a rejeitam (`claude-sonnet-5`).
- Ledger de IA completo (sucesso/falha/bloqueio, cache tokens, correlation id) em sessão própria.
- Corporate Brain + Context Engine com propósito; perfis de empresa/usuário consolidados; Learning Loop nas aprovações.
- Anti-injeção: bloco de dados externos + instrução automática; teto de IA automática por tenant/hora.
- UI: Cérebro Corporativo. API: `/api/v1/inteligencia/*`.
- Migração `af4fcaf0098f`.

## Fase 3 — API & Integration Foundation (2026-09-25)

- API de produto `/api/v1/map/*` e `/api/v1/predator/*` com chave de API por tenant (escopos, rate limit, licença e módulo no backend).
- MAP API aceita dados canônicos no corpo (CRM externo sem conector).
- Idempotência (`Idempotency-Key`), webhooks de saída assinados a partir do outbox, cron `/cron/processar-eventos`.
- Integration Hub: registro de conectores, conexões com credenciais cifradas, framework de sync incremental com retry.
- Correlation ID (`X-Request-ID`) em respostas, logs e eventos; log de acesso por requisição.
- UI: Admin → API & Webhooks.
- Migração `494a19ef8c61` (6 tabelas).

## Fase 2 — Canonical Business Model (2026-09-25)

- Modelo canônico comercial (21 entidades) e fundação de procurement (20) em `app/contexts/shared/canonical/`.
- Contrato de adapter (`app/contexts/integrations/contract.py`) e `B2BOnCrmAdapter`.
- `CanonicalMapDataSource`: MAP sobre qualquer adapter; paridade provada contra o CRM interno.
- Eventos de domínio com outbox transacional (`evento_dominio`, migração `1ca76a6cdfbc`); publicados em criação/mudança de estágio de negócio, novo cliente e aprovação de mensagem.
- Docs: 04_CANONICAL_MODEL, ENTITY_MAPPING, EVENT_MODEL, ADAPTER_CONTRACT, 17_MIGRATION_STRATEGY.

## Fase 1 — Domain Separation (2026-09-25)

- Novo pacote `app/contexts/` com `shared` (entitlements, Organization/Person),
  `crm`, `map` e `predator`, cada um com `contract.py`.
- MAP: algoritmo de risco único; economia (LTV/CAC/churn/ROI/CS) movida
  do CRM; porta `MapDataSource`; painel próprio (`/saude-contas/desempenho/*`,
  `/saude-contas/vendedores-com-contas`).
- PREDATOR: prospecção extraída de `conta_service` para
  `contexts/predator/prospeccao.py`; rotas movidas para `prospeccao_contas.py`
  (mesmos paths, gate PREDATOR).
- Gates: `exigir_algum_modulo`; contas/decisores/leads/ofertas → CRM ou
  PREDATOR; nps → MAP ou PREDATOR.
- Frontend: `PainelDesempenho` com `origem`; `MapContas` usa as rotas do MAP.
- Testes: matriz de entitlement (61), fitness function de fronteiras (4),
  skip de ffmpeg.
- CI: roda também em `staging`.
- Docs: aviso nos docs de raiz; 02/03 escritos; estado atualizado.
- **Sem migração, sem mudança de preço ou plano.**

## Fase 0 — Complete Discovery & Audit (2026-09-25)

**Código de produção alterado: nenhum.** Preços, planos e entitlements
não foram tocados.

Adicionado (só documentação, em `docs/b2bon/`):
- Estrutura de memória persistente: `00_MASTER_ARCHITECTURE.md`,
  `PROJECT_STATE.md`, `DECISIONS.md`, `OPEN_ISSUES.md`,
  `TECHNICAL_DEBT.md` e este changelog.
- Entregáveis da Fase 0: `01_CURRENT_ARCHITECTURE.md`,
  `DOMAIN_DEPENDENCY_MAP.md`, `DATABASE_MAP.md`, `MAP_CURRENT_STATE.md`,
  `PREDATOR_CURRENT_STATE.md`, `AI_CURRENT_STATE.md`,
  `PRICING_CURRENT_STATE.md`, `SECURITY_BOUNDARIES.md`.
- Placeholders `02`–`17` para as fases seguintes.
- `phases/PHASE_0_COMPLETION.md`, `phases/PHASE_1_PLAN.md`.

Principais achados: planos PREDATOR avulsos com limites 0 (OI-001);
7 acoplamentos que quebram a contratação avulsa (C1–C7); 11 de 14
chamadas de IA sem medição; preço em 3 lugares; CI não roda em `staging`.
