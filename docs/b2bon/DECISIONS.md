# DECISIONS (ADR log)

Formato: ID · data · fase · decisão · contexto · consequências · status.

## D-001 · 2026-09-25 · Fase 0 · Adotar o Master Prompt v4 como plano de evolução, com execução por fases e memória em `docs/b2bon/`
- **Contexto**: o prompt exige memória persistente fora da conversa.
- **Decisão**: `docs/b2bon/PROJECT_STATE.md` define a fase corrente.
  Só essa fase é executada. Cada fase termina com `phases/PHASE_X_COMPLETION.md`.
- **Status**: ACEITA.

## D-002 · 2026-09-25 · Fase 0 · Manter o monólito modular. Sem microserviços
- **Contexto**: 1 instância Render, sem fila, 1 banco. A auditoria não
  encontrou nenhuma necessidade de escala ou isolamento operacional que
  justifique deploy separado.
- **Decisão**: separar CRM/MAP/PREDATOR como **bounded contexts dentro
  do mesmo processo** (pacotes, contratos, eventos internos), conforme §10.
- **Consequência**: extração futura continua possível se os contratos
  forem respeitados.
- **Status**: ACEITA (PO autorizou a Fase 1 e as seguintes em 2026-09-25).

## D-003 · 2026-09-25 · Fase 0 · `docs/b2bon/` é a fonte canônica. Docs de raiz ficam como histórico
- **Contexto**: já existiam `CURRENT_ARCHITECTURE.md`,
  `AI_CURRENT_ARCHITECTURE.md`, `SECURITY_BOUNDARIES.md`,
  `DATA_FLOW_MAP.md` e `NETWORK_GAP_ANALYSIS.md` na raiz (2026-09-17),
  com trechos desatualizados (ex.: "8 pontos de IA", "única tabela sem tenant_id").
- **Decisão**: não apagar nem mover (Fase 0 não refatora). Os
  documentos novos prevalecem. Na Fase 1, adicionar um aviso no topo
  dos docs de raiz apontando para `docs/b2bon/` (TD-036).
- **Status**: ACEITA.

## D-004 · 2026-09-25 · Fase 0 · "Business Network" do Master Prompt = módulo Shoal existente
- **Contexto**: o Shoal já tem perfis, conexões, feed, intents,
  relacionamento tipado, salas corporativas e buying rooms (`sala_compra`).
- **Decisão**: as Fases 7/8/11 evoluem o Shoal. Não criam um módulo paralelo.
- **Status**: PROPOSTA (OI-008).

## D-005 · 2026-09-25 · Fase 0 · Ponto único de saída de IA já existe (`LLMProvider`). O gateway da Fase 4 evolui, não substitui
- **Contexto**: nenhum código chama o SDK Anthropic fora de `ClaudeProvider`.
- **Decisão**: a Fase 4 enriquece `LLMRequest`/`llm_helpers` em vez de
  criar uma camada paralela.
- **Status**: PROPOSTA.

## D-006 · 2026-09-25 · Fase 0 · Não corrigir OI-001 (limites 0 dos planos PREDATOR) dentro da Fase 0
- **Contexto**: o §89 proíbe alterar planos na Fase 0, mas o defeito
  afeta clientes pagantes.
- **Decisão**: registrar como OPEN ISSUE crítica e pedir autorização
  explícita do PO para um hotfix isolado, fora do fluxo de fases.
- **Status**: ACEITA.

## D-007 · 2026-09-25 · Fase 1 · Conta/Decisor/lead são Shared Kernel: rotas aceitam CRM **ou** PREDATOR
- **Contexto**: OI-004. O Kanban do CRM cria conta por `/leads/contas`
  (gate PREDATOR); a geração de lista e o enriquecimento estavam sob o
  gate do CRM.
- **Decisão**: `contas`, `decisores` e `leads` usam `_exige_organizacao`
  (CRM ou PREDATOR). Prospecção (gerar lista, enriquecer, mapear
  decisores, franquia, limite de enriquecimento) vai para o router
  `prospeccao_contas` sob `_exige_predator`. `ofertas` aceita CRM ou
  PREDATOR; `nps` aceita MAP ou PREDATOR.
- **Consequência**: tenants só-CRM deixam de ver rotas de prospecção.
  Na prática já não conseguiam usá-las: os limites dos planos CRM
  avulsos são 0. Tenants só-PREDATOR passam a gerar lista e enriquecer
  (os limites continuam dependendo de OI-001).
- **Status**: ACEITA (tomada sob a autorização geral do PO; reversível).

## D-008 · 2026-09-25 · Fase 1 · Contratos por contexto + porta de dados do MAP; fitness function obrigatória
- **Decisão**: cada contexto expõe `contract.py`. O MAP lê dados
  comerciais só por `MapDataSource`. A regra é verificada por
  `tests/unit/test_fronteiras_contexto.py` (falha o CI).
- **Consequência**: o MAP pode receber dados de CRM externo trocando só
  a implementação da porta (fundação para as Fases 3 e 13).
- **Status**: ACEITA.

## D-009 · 2026-09-25 · Fase 1 · CI roda também em `staging`
- **Contexto**: OI-005. Todo o trabalho do Master Prompt é empurrado
  para `staging`, onde nenhum teste rodava.
- **Decisão**: `ci.yml` dispara em push/PR para `master` e `staging`.
- **Status**: ACEITA.

## D-010 · 2026-09-25 · Fase 2 · Modelo canônico em Pydantic no Shared Kernel, com proveniência e classificação obrigatórias
- **Decisão**: `app/contexts/shared/canonical/`. Toda entidade herda
  `CanonicalEntity(id, tenant_id, source, origin, classification)`.
  Classificação default INTERNAL; dado interno do comprador default
  CONFIDENTIAL. Nenhuma tabela nova por entidade canônica: o canônico
  é contrato de troca, não schema de persistência.
- **Consequência**: a barreira Buy/Sell (Fase 10) e a Business Network
  (Fase 7) têm um eixo de classificação para filtrar desde já.
- **Status**: ACEITA.

## D-011 · 2026-09-25 · Fase 2 · Eventos de domínio via transactional outbox (`evento_dominio`)
- **Decisão**: `publicar` grava na mesma transação; `processar_pendentes`
  entrega fora do request, com retry e limite. Sem broker externo.
- **Consequência**: sem fila/worker (TD-032), o dispatcher roda por cron
  (Fase 3). Migrar para broker só se o volume exigir.
- **Status**: ACEITA.

## D-012 · 2026-09-25 · Fase 2 · Revision ids do Alembic são aleatórios; migração testada também em Postgres
- **Contexto**: o id "legível" `a1b2c3d4e5f6` colidiu com uma migração
  existente e criou duas heads.
- **Decisão**: gerar ids com `uuid4().hex[:12]`. Toda migração nova é
  validada em Postgres 16 local (upgrade → downgrade -1 → upgrade),
  além do teste SQLite existente.
- **Status**: ACEITA.

## D-013 · 2026-09-25 · Fase 3 · API de produto separada, autenticada por chave de API do tenant com escopos
- **Decisão**: `/api/v1/map/*` e `/api/v1/predator/*` aceitam só chave
  `b2bk_…` (hash SHA-256), com escopos por módulo/operação, rate limit
  por chave, licença e módulo checados no backend. JWT não abre a API de
  produto.
- **Consequência**: integrações de clientes não usam credencial de
  usuário humano; revogação é por chave.
- **Status**: ACEITA.

## D-014 · 2026-09-25 · Fase 3 · MAP API aceita dados canônicos no corpo
- **Decisão**: sem conector instalado, um CRM externo pode enviar
  contas/oportunidades/interações no modelo canônico e receber a análise
  do MAP, sem persistência. `tenant_id` do corpo é sempre substituído.
- **Consequência**: o MAP é consumível por CRM externo já na Fase 3
  (§11), com resultado idêntico ao do CRM interno para os mesmos dados
  (teste de contrato).
- **Status**: ACEITA.

## D-015 · 2026-09-25 · Fase 3 · Webhooks de saída consomem o outbox; só PUBLIC/INTERNAL saem
- **Decisão**: entregas únicas por (assinatura, evento), assinatura
  HMAC com timestamp, segredo criptografado em repouso, retry com backoff.
- **Status**: ACEITA.

## D-016 · 2026-09-25 · Fase 4 · Toda chamada de IA passa pelo AI Gateway, com feature registrada e roteamento C0–C3
- **Decisão**: `intel.gerar(db, llm, ContextoIA, LLMRequest)` é o único
  caminho (fitness function). C2 = modelo que já estava em produção
  (sem troca silenciosa). Quatro features curtas (FAQ, explicar match,
  sugerir regra, amostra de tom) vão para C1 (econômico).
- **Consequência**: custo atribuível por tenant/módulo/feature/agente;
  base do Usage Ledger da Fase 5. Mudança de comportamento: as 4 features
  C1 respondem com modelo menor (reversível por env).
- **Status**: ACEITA.

## D-017 · 2026-09-25 · Fase 4 · Corporate Brain sem embeddings (busca por palavra-chave)
- **Contexto**: volume pequeno por tenant; pgvector exige extensão no
  Neon e pipeline de embeddings com custo e provider adicional.
- **Decisão**: busca lexical normalizada, com propósito e orçamento no
  Context Engine. Reavaliar na Fase 17 com métrica de recall.
- **Status**: ACEITA.

## D-018 · 2026-09-25 · Fase 4 · Ledger de IA grava em sessão própria, inclusive falhas e bloqueios
- **Decisão**: o registro de uso é independente da transação do
  chamador. Falha e bloqueio por teto também são linhas do ledger.
- **Consequência**: "nenhuma chamada não contabilizada" (§82) vale mesmo
  com rollback do chamador. Em SQLite de desenvolvimento, com transação
  de escrita aberta, a gravação pode esperar o lock (TD-046).
- **Status**: ACEITA.

## D-019 · 2026-09-25 · Fase 5 · Custo do provedor em tabela versionada; créditos só com política definida pelo PO
- **Decisão**: `preco_modelo_ia` (USD/MTok, com fonte e vigência) mede o
  custo de toda chamada. A conversão para créditos fica
  `PENDING_DEFINITION` até o PO definir a taxa: o sistema não inventa preço (§71 por analogia, §55).
- **Consequência**: FinOps de custo funciona já. Carteira, excedente e
  bloqueio por saldo ficam prontos e inertes até a política ser ativada.
- **Status**: ACEITA.

## D-020 · 2026-09-25 · Fase 5 · Tenant não vê custo em USD; limite em USD é só da operação
- **Decisão**: o custo do provedor é dado interno da B2B ON. O tenant vê
  chamadas e créditos, e define limites por número de chamadas.
- **Status**: ACEITA.

## D-021 · 2026-09-25 · Fase 6 · Portfólio (`disponivel_para_venda`) separado da oferta "ativa" da cadência
- **Contexto**: `Oferta.ativo` significa "a oferta que entra no prompt de
  cadência" e só uma por tenant fica ativa. Usar isso no Next Best Offer
  reduziria o portfólio a uma oferta.
- **Decisão**: coluna nova `disponivel_para_venda` (padrão verdadeiro)
  define o portfólio do NBO/White Space. `ativo` mantém o significado.
- **Status**: ACEITA.

## D-022 · 2026-09-25 · Fase 6 · Recomendações de oportunidade são determinísticas (C0); IA só extrai necessidades
- **Decisão**: NBO, NBA, Discovery Gap, White Space e o card são regras
  explicáveis sobre dados do tenant, sem chamada de IA (custo zero,
  reprodutível, testável). A IA só propõe necessidades com citação
  literal, e elas não contam como confirmadas até revisão humana.
- **Consequência**: explicabilidade garantida por construção
  (`explicavel.recomendacao` recusa item sem evidência). Qualidade do
  casamento depende de Offer Intelligence bem preenchida.
- **Status**: ACEITA.

## D-023 · 2026-09-25 · Fase 6 · C7: riscos de pipeline e expansão com gate CRM ou PREDATOR
- **Decisão**: `/inteligencia-rede/riscos-pipeline` e `/sugestoes-expansao`
  leem só dado de CRM e passam para gate CRM-ou-PREDATOR (mesmos paths).
  `/atribuicao-receita` (sinais da rede) e o Agente Corporativo continuam
  PREDATOR até a Fase 7 definir o módulo da Business Network.
- **Status**: ACEITA.

## D-024 · 2026-09-25 · Fase 7 · Business Graph em tabelas relacionais, sem graph database
- **Contexto**: §29 pede avaliar a infraestrutura existente antes de um
  graph database. O Neo4j legado (Aura Free) pausa sozinho e só modela
  dados internos do CRM.
- **Decisão**: arestas em `relacionamento_empresarial` (com identidade,
  fonte, validade) e CONNECTED_TO derivada de `conexao_empresa`. Leitura
  por vizinhança (1 salto) com a regra única de privacidade.
- **Consequência**: sem travessias profundas por enquanto; reavaliar na
  Fase 8 (matching) com volume real.
- **Status**: ACEITA.

## D-025 · 2026-09-25 · Fase 7 · Membership como projeção de usuário → tenant
- **Decisão**: sem tabela de membros enquanto 1 usuário pertence a 1
  empresa. Papel na rede: ADMIN (admin/super_admin) ou MEMBRO (user).
- **Status**: ACEITA.

## D-026 · 2026-09-25 · Fase 7 · Identidade pública da empresa só por admin
- **Contexto**: antes qualquer usuário editava o perfil da empresa (inclusive
  o site usado na checagem de domínio da verificação) e declarava
  relacionamentos em nome dela.
- **Decisão**: editar perfil, declarar/confirmar/remover relacionamento,
  reivindicar identidade e mudar visibilidade exigem admin. A UI esconde
  essas ações para `user`.
- **Consequência**: mudança de comportamento para usuários `user`
  (reversível em `membership.ACOES_ADMIN`).
- **Status**: ACEITA.

## D-027 · 2026-09-25 · Fase 7 · Aresta `privada` é só do autor
- **Contexto**: a listagem mostrava à empresa citada as arestas privadas
  que outra empresa declarou sobre ela (ex.: "LOOKING_FOR").
- **Decisão**: `privada` = só o autor; `conexoes` passa a funcionar
  (partes + conexões do autor); bloqueio esconde conteúdo nas duas direções.
- **Status**: ACEITA.

## D-028 · 2026-09-25 · Fase 8 · Conversão de sinal é idempotente por empresa-alvo
- **Decisão**: a unidade de deduplicação é (tenant, empresa-alvo). Conta
  reaproveitada por sinal anterior/CNPJ/domínio; negócio aberto
  reaproveitado; todos os sinais da empresa fecham juntos.
- **Consequência**: "Criar oportunidade" nunca gera segunda conta ou
  segundo negócio aberto para a mesma empresa.
- **Status**: ACEITA.

## D-029 · 2026-09-25 · Fase 8 · Sala corporativa só leitura sem conexão ativa
- **Decisão**: desconectar ou bloquear congela a sala (histórico mantido
  para as duas empresas, sem novas mensagens).
- **Status**: ACEITA.

## D-030 · 2026-09-25 · Fase 9 · Módulo `bids` sem entrar em plano existente
- **Decisão**: `bids` é um módulo novo do catálogo de entitlements. Nenhum
  plano o recebe automaticamente; o super_admin o inclui num plano.
  Nenhum preço criado (§71 por analogia; catálogo na Fase 14).
- **Status**: ACEITA.

## D-031 · 2026-09-25 · Fase 9 · Proveniência calculada pelo sistema, não confiada à IA
- **Decisão**: a IA propõe citação e cláusula; o sistema só grava o que
  encontra literalmente no texto, calcula a página e descarta cláusula que
  não aparece na página. Documento com hash e fonte.
- **Status**: ACEITA.

## D-032 · 2026-09-25 · Fase 9 · PNCP experimental e desligado
- **Contexto**: o ambiente de desenvolvimento não alcança pncp.gov.br.
- **Decisão**: adapter implementado e testado com transporte simulado,
  exposto como EXPERIMENTAL e desligado (`PNCP_HABILITADO=false`) até
  validação contra a API real.
- **Status**: ACEITA.

## D-033 · 2026-09-25 · Fase 9 · Go/No-Go e matriz de conformidade determinísticos (C0)
- **Decisão**: IA só na extração de requisitos (C3). Matriz, Go/No-Go,
  prazos e concorrência são regras explicáveis sem custo de IA. A decisão
  Go/No-Go é humana, com justificativa quando diverge da recomendação.
- **Status**: ACEITA.

## D-034 · 2026-09-25 · Fase 10 · Barreira Buy/Sell estrutural + testes de comportamento
- **Decisão**: além de tenant e módulo, a barreira é garantida por
  construção: só o contexto de procurement, a API do comprador e
  `app/models` conhecem os dados do comprador (fitness function). O lado
  comprador não escreve no Corporate Brain. A única direção entre os lados
  é público → comprador (perfil público no Supplier 360).
- **Status**: ACEITA.

## D-035 · 2026-09-25 · Fase 10 · Módulo `procurement` com preço PENDING_DEFINITION
- **Decisão**: módulo no catálogo de entitlements, fora de todos os planos,
  sem preço (§71). A Fase 15 só roda com os valores do PO.
- **Status**: ACEITA.

## D-036 · 2026-09-25 · Fase 10 · Risco é sinal para revisão; regime jurídico é parâmetro
- **Decisão**: o motor de risco nunca conclui irregularidade; mensagens
  com "requer revisão". Limites que dependem do regime (fragmentação,
  prazos de alerta) vêm de `orgao_publico.parametros`; sem parâmetro, o
  sinal não é avaliado e isso é declarado.
- **Status**: ACEITA.

## D-037 · 2026-09-25 · Fase 11 · Comprador vê só o que o vendedor compartilha na sala de compra
- **Contexto**: a sala de compra mostrava ao comprador o nome interno do
  negócio e o estágio do funil do vendedor.
- **Decisão**: título e fase compartilhados, escolhidos pelo vendedor; o
  resto fica no CRM dele. Stakeholders são internos por padrão e as notas
  nunca atravessam.
- **Status**: ACEITA.

## D-038 · 2026-09-25 · Fase 11 · Permissão por usuário opcional por lado da sala
- **Decisão**: sem participantes definidos, todos os usuários da empresa
  acessam (comportamento anterior); com participantes, só eles e os admins.
  Cada empresa governa só o próprio lado.
- **Status**: ACEITA.

## D-039 · 2026-09-25 · Fase 12 · Registro de ferramentas no Shared Kernel, populado pelos contextos
- **Decisão**: o orquestrador não importa contextos de negócio; cada contexto
  registra as próprias ferramentas. Mantém a barreira Buy/Sell estrutural e
  evita ciclo de import. Coerência com o registro declarado (sensibilidade,
  agente, módulo) é validada pelo orquestrador e por teste.
- **Status**: ACEITA.

## D-040 · 2026-09-25 · Fase 12 · Roteamento determinístico primeiro; IA só como fallback e só sobre o permitido
- **Decisão**: palavras-chave (custo zero, previsível); sem rota, IA C1 com
  o catálogo das ferramentas permitidas ao usuário. A escolha da IA é
  validada contra esse catálogo. Uma ferramenta por pergunta (sem cadeia
  multi-passo por enquanto); compra × venda ambíguo pede esclarecimento.
- **Status**: ACEITA.

## D-041 · 2026-09-25 · Fase 13 · Conectores externos: somente leitura, BETA e habilitados pelo operador
- **Contexto**: os conectores são testados contra o formato documentado das
  APIs, não contra contas reais (a rede de desenvolvimento não alcança os
  provedores). §72 proíbe apresentar como disponível o que não foi validado.
- **Decisão**: conector implementado entra como BETA e só conecta quando
  listado em `CONECTORES_CRM_HABILITADOS`. Leitura apenas; os dados são
  consumidos ao vivo pelo modelo canônico (MAP por `conexao_id`), sem upsert
  no CRM interno e sem escrita no CRM externo.
- **Status**: ACEITA.

## D-042 · 2026-09-25 · Fase 13 · Hosts fixos por conector (anti-SSRF)
- **Decisão**: URLs informadas pelo tenant (ex.: `instance_url` do
  Salesforce) só são aceitas em HTTPS, porta padrão e domínio do provedor;
  o cliente HTTP não segue redirects. Campos que entram em consultas
  (ex.: `campo_cnpj`) são validados como identificadores.
- **Status**: ACEITA.

## D-043 · 2026-09-25 · Fase 13 · Segredo nunca em log nem em erro de sync
- **Contexto**: a API v1 do RD Station CRM só aceita o token na query
  string, e o `httpx` loga a URL de cada requisição.
- **Decisão**: filtro no logger `httpx` e no erro gravado pelo sync mascara
  `token`, `api_token`, `access_token`, `refresh_token` e `client_secret`.
  Onde a API permite, o segredo vai em header (Pipedrive `x-api-token`,
  Bearer nos demais).
- **Status**: ACEITA.

## D-044 · 2026-09-25 · Fase 14 · Catálogo sem preço; preço só na tabela `plano`
- **Decisão**: o catálogo diz o que existe e em que estado; o preço vem do
  plano que o checkout cobra. Produto sem plano self-service nunca aparece
  como contratável; Public Procurement fica EM_DEFINICAO até a Fase 15,
  com a estrutura de precificação vazia pronta para os valores do PO.
- **Status**: ACEITA.

## D-045 · 2026-09-25 · Fase 15 · Não executada
- **Contexto**: o Master Prompt proíbe executar a Fase 15 sem os valores do
  Product Owner ("Nunca estimar ou inventar esses valores").
- **Decisão**: fase pulada e registrada como bloqueada. O projeto segue
  para a Fase 16; a Fase 15 é executada quando o PO enviar modelo, preços,
  usuários, créditos, limites, add-ons e regras de excedente.
- **Status**: ACEITA.

## D-046 · 2026-09-25 · Fase 16 · Métricas com metodologia, sem estimativa, divididas pela barreira
- **Decisão**: toda métrica devolve metodologia e amostra; taxa sem
  denominador é nula. "Assistido por IA" e "influenciado pela rede" são
  toque registrado, não causalidade, e a interface diz isso. Métricas do
  lado comprador ficam no contexto `procurement` e nunca aparecem nas de
  receita (mesma fitness function da Fase 10).
- **Status**: ACEITA.

## D-047 · 2026-09-25 · Fase 17 · Toda FK indexada, exceto colunas de autoria
- **Contexto**: 121 FKs sem índice (o Postgres não cria sozinho): joins por
  conta/negócio e o `ON DELETE` de uma conta varriam as tabelas filhas.
- **Decisão**: indexar as 92 FKs usadas em filtro/join; ficam de fora as
  colunas de autoria (criado/aprovado/revisado/enviado por), que só custam
  escrita. Fitness function impede FK nova sem índice.
- **Status**: ACEITA.

## D-048 · 2026-09-25 · Fase 17 · Toda rota com IA tem teto
- **Decisão**: rota autenticada com IA usa `limitar_ia_por_tenant`; gatilhos
  sem usuário (webhook, cron, link público) usam o teto por hora do gateway.
  Verificado por fitness function sobre a árvore de dependências.
- **Status**: ACEITA.

## D-049 · 2026-09-25 · Fase 15 · Crédito vem do peso do workload, não do custo
- **Contexto**: a Fase 5 converteria custo em créditos (`creditos_por_usd`,
  OI-013). O PO definiu na Fase 15 um catálogo de workloads com pesos (§14).
- **Decisão**: cada feature do gateway mapeia para um workload de um catálogo
  versionado; o crédito cobrado é o peso (fixo ou variável por páginas/
  documentos). O custo real é medido à parte e só alimenta margem. A política
  `politica_creditos_ia` vira legado só leitura.
- **Consequência**: preço previsível para o cliente; margem monitorada e
  recalibrada por nova versão do catálogo, nunca automaticamente.
- **Status**: ACEITA.

## D-050 · 2026-09-25 · Fase 15 · Carteira por lotes com FEFO e reserva antes do provedor
- **Decisão**: créditos vivem em lotes (SUBSCRIPTION, TOPUP, PROMOTIONAL,
  ADJUSTMENT, ENTERPRISE_OVERAGE) com validade; consumo FEFO com desempate
  PROMOTIONAL < ADJUSTMENT < SUBSCRIPTION < TOPUP. Toda execução reserva
  antes da chamada (carteira travada com `SELECT … FOR UPDATE`), liquida no
  sucesso e libera na falha. Operação de N chamadas = uma cobrança.
  Idempotência por `(tenant, idempotency_key)` em execução, lote e movimento.
- **Status**: ACEITA.

## D-051 · 2026-09-25 · Fase 15 · Receita de referência dos créditos da assinatura
- **Contexto**: o preço do plano não é separado entre software e IA.
- **Decisão**: para margem, crédito de franquia vale R$ 6,99/1.000 (o menor
  preço efetivo da tabela de pacotes, AI 1M) — referência conservadora,
  configurável (`AI_CREDITOS_RECEITA_REF_ASSINATURA_1K_BRL`). Top-up usa o
  preço pago ÷ créditos; promocional e ajuste, zero.
- **Status**: ACEITA (revisável pelo PO).

## D-052 · 2026-09-25 · Fase 15 · Modos ENFORCE e MEASURE
- **Decisão**: produção roda ENFORCE (sem saldo, sem chamada, salvo excedente
  Enterprise aprovado). MEASURE mede tudo e registra excedente não faturável —
  usado para rollout gradual e pela suíte de testes (fixture `cobranca_ativa`
  liga ENFORCE nos testes de cobrança).
- **Status**: ACEITA.

## D-053 · 2026-09-25 · Fase 15 · Recarga automática cria pedido, não cobra fora de sessão
- **Contexto**: a integração de pagamento (preferência avulsa do Mercado Pago)
  não guarda meio de pagamento para cobrança sem o cliente presente.
- **Decisão**: com consentimento explícito (quem e quando), saldo abaixo do
  limiar cria um pedido pendente do pacote escolhido (um por vez) e o admin
  conclui o pagamento. Créditos só entram pelo webhook assinado, com valor
  conferido. Cobrança fora de sessão fica em TD-076.
- **Status**: ACEITA.

## D-054 · 2026-09-25 · Fase 15 · Franquias pendentes não concedem nada
- **Decisão**: franquias do Public Procurement (faixa 50–100K) e da Full Suite
  (75–100K) ficam PENDING_FINAL_DEFINITION por decisão do PO; nada é concedido
  por elas e as páginas mostram "Em definição". Até lá, plano de suíte recebe
  a soma das franquias dos módulos que contém. Opportunity Intelligence e
  Business Network (+10K) são add-ons não vendidos hoje: não concedem.
  O preço-base do Public Procurement segue PENDING_DEFINITION.
- **Status**: ACEITA.

## D-055 · 2026-09-26 · Correção arquitetural · Unified Strategic Sourcing Engine instead of separate Public/Private engines
- **Contexto**: a plataforma cobre quatro segmentos: B2B Sales, Public Sector Bids, Public Procurement e
  Enterprise Strategic Sourcing. Enterprise Bids também existe, como metade vendedora do Enterprise. As
  Fases 9 e 10 construíram o lado vendedor público (`bids`) e o comprador público (`procurement`) em
  paralelo: há duas tabelas de documento, dois pipelines de extração, requisito em tabela × JSON, dois
  contratos e dois workspaces (backend e UI). Enterprise RFP/RFI/RFQ ficou só como valor de `modalidade`,
  e o buy side privado não existe. Copiar cada lado para o Enterprise dobraria essa duplicação
  (≈ 4.600 linhas estimadas, `18_STRATEGIC_SOURCING.md` §6).
- **Decisão**: um núcleo `sourcing` compartilhado por Sell e Buy, Público e Enterprise, com:
  - entidade canônica `SourcingProcess` (`segment`, `side` imutável, `process_type`, `ruleset`,
    `workflow`, `metadata`) e filhos compartilhados (Document, Requirement, Evaluation, Participant,
    Proposal, Lot/Item, eventos, Contract);
  - Requirement Engine com perfis por tipo de documento;
  - Evaluation Engine com direção (SELF/PROPOSAL);
  - Matching Engine com estratégias;
  - Workflow declarativo em código e rulesets versionados separados do processo.

  Os segmentos são configuração. `bids` e `procurement` continuam como contextos para o que é
  exclusivo de cada lado. Sem tabela por tipo de processo e sem microserviço (D-002).
- **Benefícios**:
  - a lógica comum é escrita e testada uma vez;
  - Enterprise sell e buy passam a exigir só as capacidades realmente novas (convite, propostas,
    comparação, qualificação, negociação), não uma cópia;
  - regras regulatórias ficam num lugar;
  - uma UI de workspace e um conjunto de recursos de API.
- **Tradeoffs**:
  - a barreira Buy/Sell deixa de vir de "tabelas diferentes" e passa a exigir repositório com lado
    obrigatório, `side` imutável e fitness function reescrita (mais disciplina, mais testes);
  - a migração de dados precisa de Strangler (expand/backfill/leitura dupla/switch);
  - existe o risco de generalizar cedo demais, mitigado por workflow em código sem editor e por
    criar cada workflow só quando o fluxo for construído.
- **Impacto de migração**:
  - 9 tabelas migram para 9 `*_sourcing` (lote/item quando houver uso);
  - 46 rotas `/bids` e `/procurement` viram fachada e depois só ficam as de comportamento exclusivo;
  - duas telas de workspace viram `ProcessWorkspace` com painéis;
  - features de IA e workloads de crédito mantêm os códigos;
  - `audit_log`/`execucao_ia` antigos não são reescritos (mapa de ids).

  Fases S0–S8 propostas, nenhuma autorizada.
- **Status**: ACEITA como arquitetura-alvo; implementação depende do PO.

## D-056 · 2026-09-26 · Sourcing S0 · Paginação por cursor com a resposta ainda em lista
- **Contexto**: `/bids/licitacoes` e `/procurement/{recurso}` devolviam tudo. Trocar o formato da resposta
  quebraria as telas e integrações existentes.
- **Decisão**: cursor opaco *keyset* (posição da última linha), `limite` 1–500 (padrão 100), próximo cursor no
  header `X-Proximo-Cursor` (exposto no CORS). A resposta continua uma lista; as telas ganham "Carregar mais".
  Listas pequenas usadas em seletores (órgãos, planos) pedem `limite=500`.
- **Status**: ACEITA.

## D-057 · 2026-09-26 · Sourcing S2 · Barreira por repositório convive com a barreira por tabela
- **Decisão**: cada lado implementa `sourcing.repositorio.RepositorioSourcing` com o lado fixo
  (`RepositorioVenda` em `bids`, `RepositorioCompra` em `procurement`). Quem está fora de um lado lê por ele
  (FinOps e Analytics já leem a venda assim). A fitness `test_barreira_sourcing.py` roda junto com a antiga
  (`test_barreira_buy_sell.py`): tabelas de cada lado só no próprio contexto, núcleo `sourcing` neutro,
  `RepositorioCompra` só no comprador, ferramentas do agente com o lado de quem as registra.
- **Consequência**: na S3 só a implementação dos repositórios troca de tabela; chamadores e fitness não mudam.
- **Status**: ACEITA.

## D-058 · 2026-09-26 · Sourcing S3 · Expand com espelho por eventos do ORM e leitura dupla
- **Contexto**: S3 cria as tabelas unificadas sem trocar a fonte da verdade (Strangler).
- **Decisão**:
  - **Tabelas**: 6 tabelas `*_sourcing` (processo, documento, requisito, contrato, evento, evento_contrato) com
    `lado` em CHECK e imutável (evento do ORM e trigger no banco) e mapa de origem único.
  - **Espelho**: cada lado copia as próprias escritas pelos eventos do ORM (`after_insert/update/delete`), com o
    lado fixo, chamando o núcleo neutro. Roda em SAVEPOINT: falha vira log `SOURCING_ESPELHO_FALHOU` e não derruba
    a escrita do usuário.
  - **Backfill**: idempotente, em lotes, com remoção de órfãos, por `/cron/sourcing-sincronizar`. Serve para os
    dados anteriores e como rede de segurança.
  - **Leitura dupla**: os repositórios continuam respondendo pelas tabelas antigas e conferem as novas
    (`SOURCING_LEITURA_DUPLA`: COMPARAR em produção, ESTRITA na suíte).
  - **Barreira**: só o núcleo acessa as tabelas novas. Quem passa `Lado.COMPRA` ao núcleo é só o comprador;
    `Lado.VENDA`, só o vendedor (fitness).
- **Alternativas**:
  - dual-write espalhado pelos serviços: dezenas de pontos de escrita;
  - backfill periódico apenas: janela de divergência;
  - triggers de banco para copiar: regra de mapeamento duplicada em SQL por dialeto.
- **Consequência**: S6 troca a leitura para as tabelas novas sem mudar os chamadores; a duplicação de escrita
  some junto com as tabelas antigas.
- **Status**: ACEITA.

## D-059 · 2026-09-26 · Comercial · Commercial separation by job-to-be-done while sharing the Unified Strategic Sourcing Engine
- **Contexto**: OI-019 (empacotamento Enterprise) e OI-015 (empacotamento e preço do Bid Intelligence). Resolução
  do PO em 2026-09-26.
- **Decisão**: produtos organizados por job-to-be-done, tecnologia compartilhada.

  | Lado | Produto | Job-to-be-done | Preço | AI Credits/mês |
  |---|---|---|---|---|
  | SELL | **B2B ON Bid Intelligence** (Public Sector Bids + Enterprise Bids) | encontrar, qualificar, analisar e responder oportunidades públicas e privadas | R$ 1.490/mês | 25.000 |
  | BUY privado | **B2B ON Strategic Sourcing** | encontrar, qualificar, comparar e contratar fornecedores | R$ 2.990/mês, 5 buyer users | 50.000 |
  | BUY privado | **B2B ON Strategic Sourcing Enterprise** | idem, com condições enterprise | a partir de R$ 5.990/mês (STARTING_AT) | 100.000 |
  | BUY público | **B2B ON Public Procurement** | planejar e executar contratações públicas | PENDING_DEFINITION (inalterado) | PENDING_FINAL_DEFINITION (OI-017) |

  - Enterprise Bids **não** é módulo à parte: entra no Bid Intelligence sem cobrança adicional por a oportunidade
    ser pública ou privada.
  - Sem plano "Strategic Sourcing Pro" por ora.
  - Bundles futuros (Revenue & Bids; Procurement Intelligence) preparados no catálogo, sem preço.
  - Supplier Guest é papel, não consome buyer seat e só acessa o que o comprador autorizou.
  - Todos os créditos vão para a carteira única do tenant (D-050); nada de carteira por módulo.
- **Justificativa**:
  - Bid Intelligence atende o SELL SIDE; Public e Enterprise Bids são o mesmo problema do fornecedor.
  - Strategic Sourcing atende o BUY SIDE privado.
  - Public Procurement tem requisitos e rulesets próprios, mas reutiliza os engines.
- **Consequência**:
  - Continua **um** engine de sourcing (D-055). O que difere entre produtos é `segment`, `side`, `process_type`,
    `ruleset`, `workflow`, entitlement e papel, sem engine por segmento.
  - Nenhuma capacidade não implementada é exibida como disponível: o catálogo usa AVAILABLE, BETA, COMING_SOON e
    CONTACT_SALES conforme o estado real (`15_PRICING_AND_ENTITLEMENTS.md` §5).
  - A implementação comercial (planos, catálogo central, página de vendas, entitlements no código) fica para fase
    autorizada (OI-021), pela regra de fase da própria resolução.
- **Status**: ACEITA. Resolve OI-019 e OI-015.


## D-060 · 2026-09-26 · Sourcing S4 · Workflow e ruleset declarados por lado, validados por motor neutro
- **Contexto**: S4 do plano (`18_STRATEGIC_SOURCING.md` §8), autorizada pelo PO ("S4: pode trocar"). Estados de
  licitação e de processo de compra viviam em tuplas; as regras da Lei 14.133 (documentos por etapa, limites de
  sinal) em constantes soltas; as transições reservadas (GO/NO_GO, GANHA/PERDIDA) em `if`s no serviço.
- **Decisão**:
  - **Motor neutro** no núcleo: `sourcing/workflow.py` (estados, inicial, finais, transições marcadas pela ação que
    as alcança — `status`, `go_no_go`, `resultado` — e origem opcional) e `sourcing/ruleset.py` (documentos
    esperados por etapa e parâmetros com padrão, sobrescritos pela configuração do cliente). Registro por código
    versionado; registrar outra definição com o mesmo código é recusado (mudança = nova versão).
  - **Definições por lado**, porque o núcleo não conhece estado de nenhum lado e só o comprador usa
    `Lado.COMPRA`: `bids/fluxo.py` (`PUBLIC_TENDER_SELL@1`, `ENTERPRISE_RFP_SELL@1`, `PRIVATE_RFP@1`) e
    `procurement/fluxo.py` (`PUBLIC_PROCUREMENT_BUY@1`, `PUBLIC_PROCUREMENT_BR_14133@1`).
  - **Paridade**: v1 reproduz o comportamento anterior (sem restrição de origem; mesmas mensagens e códigos HTTP).
    As tuplas, `DOCUMENTOS_ESPERADOS` e as constantes viram aliases derivados; o espelho grava os códigos do
    registro.
  - `ENTERPRISE_RFP_SELL@1` é o fluxo atual aplicado ao RFP privado, com código próprio (o fluxo enterprise da S7
    nasce como nova versão). `PRIVATE_RFP@1` não tem regra: contratação privada, sem regime legal.
  - `limite_fragmentacao` não tem padrão: sem configuração do órgão, o sinal fica sem avaliação (nunca inventado).
- **Desvio de comportamento (único)**: `mudar_status` agora carrega a licitação antes de validar (o fluxo depende da
  modalidade). Licitação inexistente ou de outro tenant com status inválido/reservado responde 404 em vez de
  422/409. Não vaza nada (antes o 409 confirmava a regra sem dizer se o id existia; agora nem isso).
- **Fora do escopo**: estados de demanda, plano, item do PCA e contrato continuam em tuplas (não são processo de
  sourcing); limiares analíticos de risco sem base regulatória (`DIAS_PLANEJAMENTO`, `ACRESCIMO_ALERTA`,
  `ADITIVOS_ALERTA`, `CONCENTRACAO_ALERTA`) continuam em `riscos.py` (TD-089).
- **Status**: ACEITA.

## D-061 · 2026-09-26 · Plano unificado A–I · Phase A fecha a fundação sem tabela nova
- **Contexto**: PO autorizou S5 e OI-021 e enviou o plano "UNIFIED BUSINESS & SOURCING IMPLEMENTATION" (fases A–I,
  uma por vez). Perguntado sobre a ordem, o PO escolheu a Phase A.
- **Decisão**:
  - O plano A–I passa a ser a ordem de execução; S0–S4 contam para ele (mapa em `18_STRATEGIC_SOURCING.md` §10).
    S5 vira parte da Phase C (`ProcessWorkspace`) e OI-021 é a Phase I, ambas autorizadas e executadas na vez delas.
  - **Resolução central** (§21): `sourcing.workflow.vincular/resolver` decide workflow e ruleset por (lado,
    segmento[, tipo de processo]); o mais específico vence; sem vínculo, erro (falha fechado). A regra "RFP privado é
    Enterprise" existe só em `bids/fluxo.classificar`, usada pelo espelho e pela validação.
  - **Ruleset** (§22): versão (do código), vigência (`vigente_desde`), fonte (obrigatória) e configuração
    (parâmetros). Lei 14.133: vigente desde 2021-04-01 (art. 194); os parâmetros são padrões analíticos do produto,
    não limites legais, e isso está escrito na descrição.
  - **Entidades compartilhadas** (§6): nenhuma tabela nova. Cada entidade foi mapeada para onde já vive; Proposal,
    Evaluation, Lot, Item e Deliverable nascem com o primeiro fluxo que grava nelas (Phase C/E), como em D-058.
  - **Duplicação** (§35): eventos do ORM e backfill do espelho iguais nos dois lados foram para
    `sourcing.espelho.instalar`; cada lado declara só o mapeamento.
  - **Orçamento de desempenho** (§36): `tests/desempenho` (sob demanda) mede e compara com
    `docs/b2bon/perf/baseline.json`; `scripts/qualidade/duplicacao.py` é a análise de duplicação do projeto.
- **Alternativas**: criar as 17 entidades do §6 como tabelas agora (vazias, sem fluxo que grave: contraria §29/§49);
  resolução por `if` em cada contexto (o que §21 pede para evitar).
- **Status**: ACEITA.

## D-062 · 2026-09-26 · Phase B · Requisito normalizado com obrigatoriedade lida do trecho
- **Contexto**: Phase B do plano unificado (§38): unificar documentos, extração, requisitos, evidência,
  proveniência e base de conformidade, validando com edital público e RFP enterprise. Os engines de documento e de
  extração já eram únicos (S1); faltavam, do §18, a **obrigatoriedade** e a regra de proveniência do requisito digitado
  por humano fora do contexto de venda.
- **Decisão**:
  - `sourcing.requisitos.obrigatoriedade(trecho)`: obrigatório só com linguagem de obrigação no trecho literal
    ("deverá", "sob pena", "vedado", "must", "shall"…), desejável só com linguagem de preferência ("desejável",
    "preferencialmente", "poderá", "should"…); nenhuma ou as duas → **UNKNOWN** (`None`). Não se pergunta ao modelo:
    a obrigatoriedade tem de ser verificável no mesmo trecho que prova o requisito.
  - `sourcing.requisitos.ancorar_evidencia`: requisito manual que aponta para documento precisa do trecho no texto;
    a página é calculada. Mesmas mensagens de antes.
  - Coluna `obrigatorio` (nula) em `requisito_licitacao` e `requisito_sourcing`; chave `obrigatorio` nos achados do
    comprador. Linhas anteriores ficam UNKNOWN: a migração não infere nada; nova análise classifica.
  - Humano pode informar a obrigatoriedade no requisito manual (prevalece sobre a dedução).
  - A matriz de conformidade e a tela mostram o campo. **Go/No-Go não muda** nesta fase: usar a obrigatoriedade na
    recomendação é decisão de produto da Phase C.
- **Não feito (e por quê)**: trocar a leitura para as tabelas unificadas (TD-087/088) exige evidência de produção —
  backfill rodado e zero `SOURCING_DIVERGENCIA` por uma release — que não se obtém daqui. Fica como portão operacional.
- **Migração**: ADD/DROP COLUMN direto, sem `batch_alter_table`, para o SQLite não recriar `requisito_sourcing` e
  perder o trigger de lado imutável (coberto por teste no upgrade e no downgrade).
- **Status**: ACEITA.

## D-063 · 2026-09-26 · Phase C · Enterprise Bid por configuração, workflow v2 com negociação e proposta C0
- **Contexto**: Phase C do plano unificado (§39): concluir Public Bid + Enterprise Bid com qualificação, conformidade,
  Go/No-Go, workspace e apoio à proposta; e a UI compartilhada (§28, antiga S5).
- **Decisão**:
  - **Enterprise Bid é configuração**, não entidade: modalidades `PRIVATE_RFI`, `PRIVATE_RFQ`, `PRIVATE_TENDER` (além de
    `PRIVATE_RFP`) classificadas em (ENTERPRISE, RFI/RFQ/PRIVATE_TENDER/RFP) num único mapa (`bids/fluxo.PRIVADAS`).
  - **`ENTERPRISE_RFP_SELL@2`**: a v1 + `EM_NEGOCIACAO`, alcançável só a partir de `PROPOSTA_ENVIADA`. A v1 segue
    registrada (histórico); o vínculo do segmento aponta para a v2. O público não tem negociação (`Status inválido`).
    Em produção, as linhas espelhadas de RFP privado passam de `@1` para `@2` no próximo backfill diário; até lá a
    leitura dupla em COMPARAR pode logar essa divergência (esperada).
  - **Tela sem estados fixos**: o workspace devolve `fluxo` (código, segmento, tipo, `proximos_status`,
    `aceita_resultado`, `final`) calculado por `Workflow.proximos`; os botões de andamento vêm daí.
  - **Qualificação**: continua sendo os fatores do Go/No-Go (dados que faltam aparecem como UNKNOWN com o motivo);
    nenhuma tela ou entidade nova.
  - **Go/No-Go v2** (`bids.go_no_go.v2`): requisito técnico/comercial **obrigatório** NON_COMPLIANT é bloqueio;
    desejável ou UNKNOWN não bloqueia. Documental segue igual.
  - **Resposta por requisito** (`resposta`, texto humano; categoria nova `PERGUNTA` para RFI/questionário). A
    plataforma não escreve em nome da empresa. Log de auditoria sem o texto.
  - **Proposta C0** (`bids/proposta.py`): esboço determinístico com itens, pendências (REVISAR, RESPONDER,
    COMPROVAR), documentos do cofre a anexar e prontidão; JSON ou Markdown. Sem IA, 0 AI Credits. Proposal como
    entidade (versões, envio) fica para quando houver fluxo que grave (Phase E, lado comprador).
  - **`ProcessWorkspace`** (frontend): moldura de abas compartilhada, aba ativa na URL; licitação (Visão geral,
    Documentos, Requisitos, Conformidade, Proposta/Resposta) e processo de compra (Visão geral, Documentos, Pesquisa
    de preços, Timeline) usam o mesmo componente.
  - **E2E**: um login real por rodada (`auth.setup.ts`) reaproveitado pelas specs que não testam o login, porque o
    `/auth/login` tem rate limit por IP (5/5min) e a suíte já estava no limite. O limite não foi afrouxado.
- **Status**: ACEITA.

## D-064 · 2026-09-26 · Phase D · Lado comprador público sobre os engines, sem N+1 e com a regra à vista
- **Contexto**: Phase D (§40): demanda, planejamento, PCA, processo, fornecedor, avaliação, contrato e risco sobre os
  engines compartilhados; testar a barreira. Quase tudo existia desde a Fase 10.
- **Decisão**:
  - **TD-090 resolvido**: `precos.resumo_por_processo` e `contratos.inteligencia_em_lote` (uma consulta cada) usados
    por riscos, workspace, Supplier 360, ranking e ferramenta do agente; itens do PCA carregados de uma vez. As funções
    antigas viram atalhos para as versões em lote.
  - **Workflow e ruleset na tela do comprador**: o workspace do processo devolve `fluxo` (próximas etapas pelo
    workflow, ruleset com fonte e os **documentos que a Lei 14.133 espera na etapa atual**, presentes ou não); a aba
    Visão geral mostra o andamento com os botões vindos do servidor.
  - **Cadastro sem campo obrigatório** responde 422 com o nome do campo (derivado das colunas NOT NULL sem padrão do
    modelo), não mais 500 do banco.
  - **Avaliação**: do fornecedor, já existe (fiscalização, ocorrências, nota, Supplier 360, ranking). A avaliação de
    propostas usa a entidade compartilhada que nasce na Phase E (lado comprador) e vale também para o processo
    público — nada criado aqui para não haver duas.
- **Barreira**: testes estendidos às superfícies novas (esboço de proposta JSON/Markdown, resposta do vendedor,
  bloco `fluxo`) nos dois sentidos, no mesmo tenant com os dois módulos.
- **Status**: ACEITA.

## D-065 · 2026-09-26 · Phase E · Enterprise Strategic Sourcing nativo no modelo unificado
- **Contexto**: Phase E (§41): Strategic Sourcing, descoberta, RFI/RFP/RFQ, qualificação, comparação, shortlist,
  negociação, contrato — produto novo, sem tabela antiga.
- **Decisão**:
  - **Nativo no modelo unificado**: o comprador privado grava direto em `*_sourcing` (processo, requisito, contrato
    com `origem_tabela = "nativo"`; espelho, backfill e leitura dupla nunca tocam essas linhas). Só o núcleo acessa as
    tabelas: `sourcing/nativo.py` (criar/obter/listar/atualizar por nome de entidade, **sempre filtrando tenant e
    lado**). A lógica de compra fica no lado comprador (`procurement/estrategico.py`, `Lado.COMPRA`).
  - **Entidades que nascem aqui** (D-058/D-061): participante, item, proposta (uma linha por rodada), preço por
    item e avaliação (proposta × requisito: resposta do fornecedor + status/nota/justificativa do comprador), todas
    com `lado` em CHECK e imutável (trigger + ORM); `peso` no requisito.
  - **Um workflow por natureza** (§21), escolhido pelo vínculo (lado, segmento, tipo): `ENTERPRISE_SOURCING_BUY@1`
    (RFP, concorrência privada, evento estratégico), `ENTERPRISE_RFQ_BUY@1` (cotação leve: sem avaliação técnica nem
    shortlist, §15), `ENTERPRISE_RFI_BUY@1` (RFI, EOI, qualificação: coleta e encerra, sem adjudicação). Ruleset
    `ENTERPRISE_SOURCING_POLICY@1` (política do próprio cliente, sem parâmetro inventado).
  - **Aprovação humana antes da adjudicação**: pedido com justificativa → administrador aprova (adjudica e marca os
    demais como não selecionados) ou recusa com motivo (volta à etapa anterior). Decisão sempre humana.
  - **Descoberta (§16)** pelo Matching Engine (estratégia nova `criterios_fornecedor`): cadastro interno do comprador
    e perfis da Business Network **que ele pode ver** (diretório ou conexões, sem bloqueados; só campos públicos).
    Empresa oculta não aparece nem pode ser convidada. Nada do processo vai para a rede.
  - **Comparação (§20)** determinística (C0): obrigatórios atendidos, nota ponderada pelos pesos, valor, prazo,
    pagamento, risco; destaques (menor valor, maior nota) só entre quem não falhou obrigatório. Sem vencedor automático.
  - **Gate** `sourcing` (Strategic Sourcing); API em `/sourcing` (§30). O preço e o plano comercial ficam na Phase I.
  - **Fitness**: `app/api/v1/strategic_sourcing.py` declarado como API do lado comprador; regex das tabelas unificadas
    inclui as novas.
  - Provisório de `origem_id` na inserção nativa é negativo e único (não zero), para inserções concorrentes não
    esperarem umas pelas outras no índice único (provado em Postgres).
- **Fora do escopo**: portal do fornecedor (Phase F), IA de avaliação/comparação (Phase G), documentos anexados às
  propostas (fica para a Phase F, com o acesso do fornecedor).
- **Status**: ACEITA.
